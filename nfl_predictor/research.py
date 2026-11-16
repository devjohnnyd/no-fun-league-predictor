"""Chronological feature-family tests, probability calibration and error analysis."""
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .engine import FAMILIES, FeatureEngine
from .features import BASE_NAMES
from .model import fit, predict, scores
from .market import elo_probability, remove_margin
from .storage import clean, read_json, sha256, write_new


def feature_frame(dataset, venues=None):
    engine = FeatureEngine(dataset, venues)
    start = min(g["season"] for g in dataset["schedule"]) + 1
    rows = []
    for game in sorted(dataset["schedule"], key=lambda g: (g["season"], g["week"], g["game_id"])):
        if game["season"] < start or game.get("home_score") is None or (game["game_id"], game["home_team"]) not in engine.team_by_game:
            continue
        features, detail = engine.features(game)
        target = .5 if game["home_score"] == game["away_score"] else int(game["home_score"] > game["away_score"])
        rows.append({"game_id": game["game_id"], "season": game["season"], "week": game["week"],
                     "home": game["home_team"], "away": game["away_team"], "target": target, **features,
                     "home_qb_db": detail["home_qb"]["effective_dropbacks"], "away_qb_db": detail["away_qb"]["effective_dropbacks"],
                     "injury_load": sum(detail[side + "_injuries"][kind] for side in ("home", "away") for kind in ("ol_out", "skill_out", "def_out")),
                     "wind": detail["weather"]["wind_mph"], "short_rest": min(game.get("home_rest") or 7, game.get("away_rest") or 7) <= 5,
                     "visitor_time_shift": detail["away_travel"].get("clock_shift"),
                     "visitor_early_clock": detail["away_travel"].get("early_clock"),
                     "visitor_late_clock": detail["away_travel"].get("late_clock"),
                     "neutral": game.get("location") == "Neutral"})
    frame = pd.DataFrame(rows)
    if frame.empty or frame.game_id.duplicated().any():
        raise ValueError("Empty or duplicate feature matrix")
    return frame


def rolling(frame, season, names, alpha, through_week=18):
    decisive = frame[frame.target.isin([0, 1])]
    result = []
    weeks = sorted(decisive.loc[decisive.season.eq(season) & decisive.week.le(through_week), "week"].unique())
    for week in weeks:
        train = decisive[(decisive.season < season) | (decisive.season.eq(season) & (decisive.week < week))]
        test = decisive[decisive.season.eq(season) & decisive.week.eq(week)]
        if train.empty:
            continue
        model = fit(train, names, alpha)
        part = test.copy()
        part["p"] = predict(model, test)
        part["training_rows"] = len(train)
        part["training_last_season"] = int(train.season.max())
        part["training_last_week"] = int(train.loc[train.season.eq(train.season.max()), "week"].max())
        result.append(part)
    if not result:
        raise ValueError(f"No evaluation games for {season}")
    return pd.concat(result, ignore_index=True)


def logit(probabilities):
    p = np.clip(np.asarray(probabilities, dtype=float), 1e-8, 1 - 1e-8)
    return np.log(p / (1 - p))


def calibrate_fit(rows):
    return fit(pd.DataFrame({"logit": logit(rows.p), "target": rows.target.to_numpy(float)}), ["logit"], 1.)


def calibrated(calibrator, probabilities):
    return predict(calibrator, pd.DataFrame({"logit": logit(probabilities)}))


def model_probabilities(artifact, frame):
    values = predict(artifact["model"], frame)
    return calibrated(artifact["calibration"], values) if artifact.get("calibration") else values


def reliability(y, p):
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    favorite = np.maximum(p, 1 - p)
    correct = ((p >= .5) == y).astype(int)
    bins = []
    for low, high in ((.5, .6), (.6, .7), (.7, .8), (.8, .9), (.9, 1.000001)):
        mask = (favorite >= low) & (favorite < high)
        n, wins = int(mask.sum()), int(correct[mask].sum())
        interval = None
        if n:
            z, fraction = 1.95996398454, wins / n
            center = (fraction + z * z / (2 * n)) / (1 + z * z / n)
            margin = z * np.sqrt(fraction * (1 - fraction) / n + z * z / (4 * n * n)) / (1 + z * z / n)
            interval = [float(max(0, center - margin)), float(min(1, center + margin))]
        bins.append({"low": low, "high": min(1., high), "games": n, "correct": wins,
                     "mean_probability": float(favorite[mask].mean()) if n else None,
                     "observed_accuracy": wins / n if n else None, "accuracy_wilson_95": interval})
    return bins


def paired_brier(rows, baseline, samples=2000):
    joined = rows[["game_id", "week", "target", "p"]].merge(baseline[["game_id", "p"]], on="game_id", suffixes=("", "_baseline"), validate="one_to_one")
    joined["delta"] = (joined.p - joined.target) ** 2 - (joined.p_baseline - joined.target) ** 2
    weeks = [group.delta.to_numpy() for _, group in joined.groupby("week")]
    if not weeks:
        return {"games": 0, "delta_brier": None, "week_bootstrap_95": None}
    rng = np.random.default_rng(20261115)
    sums = np.array([x.sum() for x in weeks])
    counts = np.array([len(x) for x in weeks])
    draw = rng.integers(0, len(weeks), size=(samples, len(weeks)))
    boot = sums[draw].sum(axis=1) / counts[draw].sum(axis=1)
    return {"games": len(joined), "delta_brier": float(joined.delta.mean()),
            "week_bootstrap_95": np.quantile(boot, [.025, .975]).tolist(),
            "meaning": "Candidate minus baseline; negative is better. Resampling unit is NFL week."}


def error_slices(rows):
    slices = {
        "all": np.ones(len(rows), dtype=bool),
        "home_favorite": rows.p.ge(.5), "road_favorite": rows.p.lt(.5),
        "low_sample_qb": rows.home_qb_db.lt(30) | rows.away_qb_db.lt(30),
        "high_injury_load": rows.injury_load.ge(2), "wind_at_least_15mph": rows.wind.ge(15),
        "short_rest": rows.short_rest.eq(True), "neutral_site": rows.neutral.eq(True),
        "confidence_at_least_70pct": np.maximum(rows.p, 1 - rows.p) >= .7,
        "visitor_two_or_more_time_zones": rows.visitor_time_shift.abs().ge(2),
        "visitor_eastward_early_home_clock": rows.visitor_time_shift.ge(2) & rows.visitor_early_clock.gt(0),
        "visitor_westward_late_home_clock": rows.visitor_time_shift.le(-2) & rows.visitor_late_clock.gt(0),
    }
    return [{"slice": name, **scores(rows.loc[mask, "target"], rows.loc[mask, "p"])} for name, mask in slices.items()]


def research(dataset_path, output, season=2026, week=10, venues_path=None):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    dataset = read_json(dataset_path)
    venues = read_json(venues_path) if venues_path else None
    frame = feature_frame(dataset, venues)
    tune_year, select_year = season - 2, season - 1
    initial = frame[frame.season.lt(tune_year)]
    all_names = list(dict.fromkeys(BASE_NAMES + [n for names in FAMILIES.values() for n in names]))
    eligible = [n for n in all_names if initial[n].notna().sum() >= 30 and initial[n].dropna().std() > 1e-8]
    excluded = {n: "Fewer than 30 initial-training observations or no observed variation; not fitted" for n in all_names if n not in eligible}
    groups = {"efficiency_qb": BASE_NAMES[:11], "v2_baseline": BASE_NAMES,
              **{name: BASE_NAMES + names for name, names in FAMILIES.items()}, "combined": all_names}
    groups = {name: [n for n in names if n in eligible] for name, names in groups.items()}
    tune, selection, calibration, alphas, diagnostic, diagnostics = [], [], {}, {}, {}, []
    for family, names in groups.items():
        if not names:
            continue
        tuned = {}
        for alpha in (15., 60., 150.):
            rows = rolling(frame, tune_year, names, alpha)
            tuned[alpha] = rows
            tune.append({"family": family, "alpha": alpha, **scores(rows.target, rows.p)})
        best = min((r for r in tune if r["family"] == family), key=lambda r: r["brier"])
        alphas[family] = best["alpha"]
        calibration[family] = calibrate_fit(tuned[best["alpha"]])
        val = rolling(frame, select_year, names, best["alpha"])
        selection.append({"family": family, "calibrated": False, "alpha": best["alpha"], **scores(val.target, val.p)})
        selection.append({"family": family, "calibrated": True, "alpha": best["alpha"],
                          **scores(val.target, calibrated(calibration[family], val.p))})
        rows = rolling(frame, season, names, best["alpha"], through_week=week - 1)
        diagnostic[family] = rows
        diagnostics.append({"family": family, "calibrated": False, "alpha": best["alpha"], **scores(rows.target, rows.p)})
        diagnostics.append({"family": family, "calibrated": True, "alpha": best["alpha"],
                            **scores(rows.target, calibrated(calibration[family], rows.p))})
        print(f"Evaluated {family}", flush=True)
    selected = min(selection, key=lambda r: r["brier"])
    current = frame[((frame.season < season) | (frame.season.eq(season) & frame.week.lt(week))) & frame.target.isin([0, 1])]
    models = {}
    for family, names in groups.items():
        if names:
            models[family] = {"model": fit(current, names, alphas[family]), "calibration": None,
                              "family": family, "training_games": len(current),
                              "training_cutoff": {"season": season, "before_week": week},
                              "status": "baseline" if family == "v2_baseline" else "shadow"}
    selected_key = selected["family"]
    if selected["calibrated"]:
        selected_key += "_calibrated"
        models[selected_key] = {**models[selected["family"]], "calibration": calibration[selected["family"]], "status": "shadow"}
    baseline = diagnostic["v2_baseline"]
    winner = diagnostic[selected["family"]].copy()
    if selected["calibrated"]:
        winner["p"] = calibrated(calibration[selected["family"]], winner.p)
    weekly = [{"week": int(w), **scores(group.target, group.p)} for w, group in winner.groupby("week")]
    schedule_by_id = {g["game_id"]: g for g in dataset["schedule"]}
    elo = baseline.copy()
    elo["p"] = [elo_probability(dataset, schedule_by_id[gid]) for gid in elo.game_id]
    market_rows = []
    for row in baseline.to_dict("records"):
        game = schedule_by_id[row["game_id"]]
        try:
            p = remove_margin(game["home_moneyline"], game["away_moneyline"])["home_probability"]
            market_rows.append({**row, "p": p})
        except (ValueError, TypeError):
            continue
    untimed_market = pd.DataFrame(market_rows)
    worst = winner.copy()
    worst["brier_contribution"] = (worst.p - worst.target) ** 2
    report = {
        "version": "4.0.0", "created_at": datetime.now(timezone.utc).isoformat(),
        "policy": {"penalty_tuning_year": tune_year, "feature_selection_year": select_year,
                   "calibration_fit": f"{tune_year} out-of-week probabilities only",
                   "diagnostic_season": season, "diagnostic_through_week": week - 1,
                   "status": "Retrospective research designed after live Week 10 outcomes; no untouched test is claimed",
                   "primary_forecasts": "v2 feature family rebuilt from fresh data; new families remain shadow models"},
        "selected": selected, "selected_key": selected_key, "models": models,
        "tuning": tune, "selection": selection, "diagnostics": diagnostics,
        "candidate_vs_baseline": [{"family": name, **paired_brier(rows, baseline)} for name, rows in diagnostic.items()],
        "selected_vs_baseline": paired_brier(winner, baseline), "calibration": reliability(winner.target, winner.p),
        "baseline_calibration": reliability(baseline.target, baseline.p),
        "baseline_error_slices": error_slices(baseline),
        "independent_elo": {**scores(elo.target, elo.p), "comparison": paired_brier(elo, baseline),
                             "method": "K=20, home advantage=55 Elo points, offseason carry=0.67; prior weeks only"},
        "untimed_historical_market": {**scores(untimed_market.target, untimed_market.p),
                                      "warning": "Schedule moneyline timestamps are unknown; descriptive closing-line benchmark only, not a time-aligned prospective comparison"} if market_rows else {"games": 0},
        "error_slices": error_slices(winner), "weekly": weekly,
        "largest_probability_errors": clean(worst.sort_values("brier_contribution", ascending=False)[["game_id", "home", "away", "target", "p", "brier_contribution"]].head(15).to_dict("records")),
        "excluded_features": excluded, "feature_coverage": {n: int(frame[n].notna().sum()) for n in all_names},
        "quality": dataset["quality"], "source_sha256": {"dataset": sha256(dataset_path), "venues": sha256(venues_path) if venues_path else None},
        "historical_timing": dataset["historical_timing"],
        "limitations": [
            "Final historical injuries, recorded starting QBs and observed weather are not timestamped pregame observations.",
            "FTN date_pulled is a retrieval time, not proof of first publication; historical charting availability is not prospectively verified.",
            "PFR pressure percentages are averaged using eligible nflverse dropbacks as exposure weights; the source universes differ. Impossible source percentages are excluded.",
            "Replacement identities inferred from prior snap leaders are proxies. Live depth-slot matches override them where available; OL/defensive player quality is not invented.",
            "Tracking feeds omit low-attempt players. Missing backup quality is unknown, and is not scored as measured average performance.",
            "City-level travel is a distance/body-clock proxy; actual team itineraries are unavailable.",
            "Precipitation interactions are computed live but excluded from fitting until varying historical inputs exist.",
            "Confidence bands show sampling uncertainty in observed accuracy; scenario ranges are not probability confidence intervals.",
            "Paired week-bootstrap intervals are exploratory comparisons, not multiple-testing-adjusted proof of feature value.",
        ], "attribution": dataset["attribution"]}
    output.mkdir(parents=True)
    write_new(output / "research.json", report)
    frame.to_csv(output / "features.csv", index=False)
    winner.to_csv(output / "diagnostic-predictions.csv", index=False)
    rows = ["# Model research v4", "", "New families are shadow candidates. Historical results use revised public data and timing assumptions; no prospective improvement is claimed.", "", "| Family | Calibrated | Selection Brier | Correct / games |", "|---|---|---:|---:|"]
    for row in sorted(selection, key=lambda r: r["brier"]):
        rows.append(f"| {row['family']} | {row['calibrated']} | {row['brier']:.6f} | {row['correct']} / {row['games']} |")
    rows += ["", f"Selected research configuration: **{selected_key}**. Primary future forecasts retain the v2 feature family with freshly rebuilt inputs.", "", "See `research.json` for chronological policy, paired comparisons, calibration, error slices, source coverage and limitations."]
    (output / "README.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return report
