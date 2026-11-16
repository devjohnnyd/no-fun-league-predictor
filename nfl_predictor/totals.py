"""Separate chronological total-points research and weekly brochure tracking."""
from datetime import datetime, timezone
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .engine import FeatureEngine
from .freshness import timestamp
from .model import design
from .storage import clean, read_json, sha256, write_new

CORE = ["offense_sum", "defense_sum", "qb_epa_sum", "qb_cpoe_sum", "pace_sum", "pass_rate_sum", "explosive_sum", "sack_sum"]
CONTEXT = ["wind", "cold", "ol_absences", "skill_absences", "def_absences", "qb_low_sample", "short_rest", "clock_exposure"]


def total_features(engine, game, context=None, detail=None):
    if detail is None:
        _, detail = engine.features(game, context)
    hs, aws = detail["home_state"], detail["away_state"]
    hq, aq = detail["home_qb"], detail["away_qb"]
    pace = []
    for team in (game["home_team"], game["away_team"]):
        rows = engine.weighted(team, game["season"], game["week"])
        exposure = sum(weight for _, weight in rows)
        pace.append(sum(row["plays"] * weight for row, weight in rows) / exposure if exposure else None)
    weather = detail["weather"]
    wind = weather["wind_mph"] if weather["outdoor"] else 0.
    temp = weather["temperature_f"]
    injuries = [detail[side + "_injuries"] for side in ("home", "away")]
    travel = [detail[side + "_travel"] for side in ("home", "away")]
    clock = [row.get("early_clock") for row in travel] + [row.get("late_clock") for row in travel]
    return {"offense_sum": hs["off_epa"] + aws["off_epa"], "defense_sum": hs["def_epa"] + aws["def_epa"],
            "qb_epa_sum": hq["epa"] + aq["epa"], "qb_cpoe_sum": hq["cpoe"] + aq["cpoe"],
            "pace_sum": sum(pace) if all(p is not None for p in pace) else None,
            "pass_rate_sum": hs["pass_rate"] + aws["pass_rate"], "explosive_sum": hs["explosive"] + aws["explosive"],
            "sack_sum": hs["sack_rate"] + aws["sack_rate"], "wind": wind,
            "cold": max(0, 45 - temp) if temp is not None and weather["outdoor"] else None if weather["outdoor"] else 0.,
            "ol_absences": sum(row["ol_out"] for row in injuries), "skill_absences": sum(row["skill_out"] for row in injuries),
            "def_absences": sum(row["def_out"] for row in injuries), "qb_low_sample": hq["new"] + aq["new"],
            "short_rest": min(game.get("home_rest") or 7, game.get("away_rest") or 7),
            "clock_exposure": sum(clock) if all(v is not None for v in clock) else None}


def fit_total(frame, names, alpha):
    matrix, medians, mean, scale = design(frame, names)
    penalty = np.eye(matrix.shape[1]) * alpha
    penalty[0, 0] = 1e-8
    beta = np.linalg.solve(matrix.T @ matrix + penalty, matrix.T @ frame.total.to_numpy(float))
    return {"names": names, "medians": medians.tolist(), "mean": mean.tolist(), "scale": scale.tolist(), "beta": beta.tolist(), "alpha": alpha}


def predict_total(model, frame):
    matrix, *_ = design(frame, model["names"], model["medians"], model["mean"], model["scale"])
    return np.maximum(0, matrix @ np.asarray(model["beta"]))


def total_scores(rows):
    if rows.empty:
        return {"games": 0, "mae": None, "rmse": None, "mean_error": None}
    error = rows.total.to_numpy(float) - rows.predicted.to_numpy(float)
    return {"games": len(rows), "mae": float(np.mean(np.abs(error))), "rmse": float(np.sqrt(np.mean(error ** 2))),
            "mean_error": float(np.mean(error))}


def rolling_totals(frame, year, names, alpha, through_week=18, allow_empty=False):
    output = []
    for week in sorted(frame.loc[frame.season.eq(year) & frame.week.le(through_week), "week"].unique()):
        train = frame[(frame.season < year) | (frame.season.eq(year) & frame.week.lt(week))]
        test = frame[frame.season.eq(year) & frame.week.eq(week)].copy()
        if train.empty:
            continue
        test["predicted"] = predict_total(fit_total(train, names, alpha), test)
        test["mean_baseline"] = train.total.mean()
        output.append(test)
    if not output:
        if allow_empty and through_week == 0:
            return frame.iloc[:0].copy().assign(predicted=pd.Series(dtype=float), mean_baseline=pd.Series(dtype=float))
        raise ValueError("No rolling total-points evaluation rows")
    return pd.concat(output, ignore_index=True)


def projection(model, features):
    mean = float(predict_total(model["model"], pd.DataFrame([features]))[0])
    samples = np.maximum(0, np.rint(mean + np.asarray(model["residuals"], dtype=float))).astype(int)
    return {"projected_total": mean, "interval_80": np.quantile(samples, [.1, .9]).tolist(),
            "total_samples": samples.tolist(), "calibration_games": len(samples), "status": "experimental",
            "interval_meaning": "Empirical predictive range from earlier out-of-week residuals; not a confidence interval or guarantee"}


def line_analysis(projection_row, line):
    line = float(line)
    if not math.isfinite(line) or not 0 < line < 150 or not (line * 2).is_integer():
        raise ValueError("Total line must be a positive whole or half point below 150")
    samples = np.asarray(projection_row["total_samples"], dtype=float)
    if not len(samples) or not np.isfinite(samples).all():
        raise ValueError("Missing total-points predictive distribution")
    whole = line.is_integer()
    denominator = len(samples) + (3 if whole else 2)
    over = (int((samples > line).sum()) + 1) / denominator
    under = (int((samples < line).sum()) + 1) / denominator
    push = (int((samples == line).sum()) + 1) / denominator if whole else 0.
    return {"line": line, "over_probability": over, "under_probability": under, "push_probability": push,
            "lean": "Over" if over > under else "Under" if under > over else "Even", "experimental": True}


def research_totals(dataset_path, venues_path, season, week, output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    dataset, venues = read_json(dataset_path), read_json(venues_path)
    engine, rows = FeatureEngine(dataset, venues), []
    for game in sorted(dataset["schedule"], key=lambda g: (g["season"], g["week"], g["game_id"])):
        if game["season"] < 2023 or game.get("home_score") is None or (game["game_id"], game["home_team"]) not in engine.team_by_game:
            continue
        rows.append({"game_id": game["game_id"], "season": game["season"], "week": game["week"],
                     "total": game["home_score"] + game["away_score"], **total_features(engine, game)})
    frame = pd.DataFrame(rows)
    tuning, selection, candidates, residuals = [], [], {}, {}
    for family, names in (("efficiency_pace", CORE), ("context", CORE + CONTEXT)):
        eligible = [name for name in names if frame.loc[frame.season.eq(2023), name].notna().sum() >= 30 and frame.loc[frame.season.eq(2023), name].nunique() > 1]
        tuning_rows = {}
        for alpha in (15., 60., 150.):
            evaluated = rolling_totals(frame, 2024, eligible, alpha)
            tuning.append({"family": family, "alpha": alpha, **total_scores(evaluated)})
            tuning_rows[alpha] = evaluated
        best = min((row for row in tuning if row["family"] == family), key=lambda r: r["mae"])
        validation = rolling_totals(frame, 2025, eligible, best["alpha"])
        errors = (tuning_rows[best["alpha"]].total - tuning_rows[best["alpha"]].predicted).to_numpy()
        bounds = np.quantile(errors, [.1, .9])
        observed = validation.total - validation.predicted
        selection.append({"family": family, "alpha": best["alpha"], **total_scores(validation),
                          "interval_80_coverage": float(((observed >= bounds[0]) & (observed <= bounds[1])).mean())})
        candidates[family] = (eligible, best["alpha"])
        residuals[family] = errors.tolist()
    selected = min(selection, key=lambda r: r["mae"])
    names, alpha = candidates[selected["family"]]
    diagnostic = rolling_totals(frame, season, names, alpha, week - 1, allow_empty=week == 1)
    mean_baseline = diagnostic.copy()
    mean_baseline["predicted"] = mean_baseline.mean_baseline
    train = frame[(frame.season < season) | (frame.season.eq(season) & frame.week.lt(week))]
    result = {"version": "4.0.0", "created_at": datetime.now(timezone.utc).isoformat(), "status": "experimental",
              "training_cutoff": {"season": season, "before_week": week}, "model": fit_total(train, names, alpha),
              "training_games": len(train), "residuals": residuals[selected["family"]], "selected": selected,
              "tuning": tuning, "selection": selection, "diagnostic": total_scores(diagnostic),
              "mean_baseline_diagnostic": total_scores(mean_baseline),
              "source_sha256": {"dataset": sha256(dataset_path), "venues": sha256(venues_path)},
              "policy": "Separate ridge total-points regression; 2024 MAE tuning and OOF residuals, 2025 family selection, previously examined 2026 diagnostics. NFL ties included. Historical timing assumptions match winner research.",
              "limitations": ["No timestamped historical brochure lines: no claim of validated over/under accuracy or betting edge.",
                              "Empirical residual probabilities are experimental; normal score distributions and independence between games are not assumed.",
                              "Whole-point pushes are separate; brochure settlement rules require the actual card terms.",
                              "Do not multiply individual game probabilities to claim a perfect-card chance."],
              "attribution": dataset["attribution"]}
    output.mkdir(parents=True)
    write_new(output / "totals-model.json", result)
    diagnostic.to_csv(output / "diagnostic-predictions.csv", index=False)
    return result


def total_forecasts(batches, latest=False):
    """Select original (or latest) total projections independently of winner revisions."""
    selected = {}
    for batch in batches:
        issued = batch.get("issued_at")
        if not issued or len(issued) <= 10:
            continue
        for row in batch["forecast"]:
            event = str(row["espn_id"])
            if row.get("total_projection") and (event not in selected or (timestamp(issued) > timestamp(selected[event]["issued_at"]) if latest else timestamp(issued) < timestamp(selected[event]["issued_at"]))):
                selected[event] = {**row, "issued_at": issued}
    return selected


def saved_total_pick(card, selection, forecast, issued_at):
    """Freeze an exact-line choice at release, without using game outcomes."""
    if not card.get("received_at") or not timestamp(card["received_at"]) <= timestamp(issued_at) < timestamp(forecast["kickoff"]):
        raise ValueError("A total pick requires the printed line before release and release before kickoff")
    if (selection["home"], selection["away"]) != (forecast["home"], forecast["away"]):
        raise ValueError("Total pick team identity mismatch")
    return {**line_analysis(forecast["total_projection"], selection["line"]),
            "issued_at": issued_at, "line_received_at": card["received_at"], "source": card.get("source")}


def card_rows(card, games, forecasts):
    """Score printed lines; never manufacture predictions for completed games."""
    if not card:
        return []
    selections = card.get("games", [])
    if len(selections) != 3 or len({str(row["event_id"]) for row in selections}) != 3:
        raise ValueError("A weekly brochure card requires exactly three distinct games")
    by_id = {str(g["event_id"]): g for g in games}
    output = []
    for selection in selections:
        event, line = str(selection["event_id"]), float(selection["line"])
        if not math.isfinite(line) or not 0 < line < 150 or not (line * 2).is_integer():
            raise ValueError("Invalid brochure total")
        game = by_id.get(event)
        if not game or (selection["home"], selection["away"]) != (game["home"], game["away"]):
            raise ValueError("Brochure game identity does not match this week")
        completed = game.get("completed") is True
        total = game["home_score"] + game["away_score"] if completed else None
        live_scores = [game.get(side + "_live_score") for side in ("home", "away")]
        live_total = sum(live_scores) if game.get("state") == "in" and all(value is not None for value in live_scores) else None
        actual = "Over" if total is not None and total > line else "Under" if total is not None and total < line else "Push" if total is not None else None
        forecast = forecasts.get(event, {})
        projection_row = forecast.get("total_projection")
        if projection_row and (forecast.get("home"), forecast.get("away")) != (game["home"], game["away"]):
            raise ValueError("Total-points forecast team identity mismatch")
        # The timestamp of learning a brochure line matters as well as the model.
        timely_line = bool(card.get("received_at") and timestamp(card["received_at"]) < timestamp(game["kickoff"]))
        issued_at = forecast.get("issued_at")
        timely_forecast = bool(issued_at and len(issued_at) > 10 and timestamp(issued_at) < timestamp(game["kickoff"]))
        analysis = line_analysis(projection_row, line) if projection_row and timely_line and timely_forecast else None
        saved = forecast.get("total_pick")
        if saved:
            if float(saved["line"]) != line or saved["issued_at"] != issued_at or saved["line_received_at"] != card.get("received_at"):
                raise ValueError("Saved total pick differs from the recorded printed line or timestamps")
            if not analysis or any(saved[key] != analysis[key] for key in ("lean", "over_probability", "under_probability", "push_probability")):
                raise ValueError("Saved total pick differs from its predictive distribution")
        user = selection.get("user_pick")
        if user and (user.get("pick") not in {"Over", "Under"} or not user.get("reported_at") or not user.get("source")):
            raise ValueError("User total pick requires Over/Under, report timestamp and source")
        if user:
            timestamp(user["reported_at"])
        output.append({"selectionId": f"{card['season']}:{card['week']}:{event}:total:{line:g}", "kind": "total",
                       "season": card["season"], "week": card["week"], "kickoff": game["kickoff"],
                       "eventId": event, "homeCode": game["home"], "awayCode": game["away"], "line": line,
                       "liveTotal": live_total, "statusDetail": game.get("status_detail"),
                       "actualTotal": total, "actualOutcome": actual, "state": game["state"],
                       "userPick": user["pick"] if user else None,
                       "userReportedAt": user["reported_at"] if user else None,
                       "userPickSource": user["source"] if user else None,
                       "userReportedAfterKickoff": timestamp(user["reported_at"]) >= timestamp(game["kickoff"]) if user else None,
                       "userCorrect": user["pick"] == actual if user and actual in {"Over", "Under"} else None,
                       "projection": projection_row, "analysis": analysis,
                       "predictionStatus": "No directional lean (50/50)" if analysis and analysis["lean"] == "Even" else "Experimental pregame model" if analysis else "No pregame forecast recorded",
                       "source": card.get("source"), "lineReceivedAt": card.get("received_at"),
                       "forecastIssuedAt": issued_at if projection_row else None,
                       "correct": (analysis["lean"] == actual) if analysis and analysis["lean"] != "Even" and actual in {"Over", "Under"} else None})
    return output


def score_card(card, batches, results):
    from .model import scores
    if (card["season"], card["week"]) != (results["season"], results["week"]):
        raise ValueError("Brochure and results season/week differ")
    forecasts = total_forecasts(batches)
    rows = card_rows(card, results["games"], forecasts)
    decided = [row for row in rows if row["correct"] is not None]
    probabilities = [row["analysis"]["over_probability"] / (row["analysis"]["over_probability"] + row["analysis"]["under_probability"]) for row in decided]
    return {"season": card["season"], "week": card["week"], "results_retrieved_at": results["retrieved_at"],
            "games": rows, "metrics": scores([int(row["actualOutcome"] == "Over") for row in decided], probabilities),
            "user_record": user_record(rows),
            "pushes": sum(row["actualOutcome"] == "Push" for row in rows),
            "abstentions": sum(bool(row["analysis"]) and row["analysis"]["lean"] == "Even" for row in rows),
            "unavailable_predictions": sum(row["analysis"] is None for row in rows),
            "pending": sum(row["actualOutcome"] is None for row in rows),
            "policy": "Only timestamped pregame directional picks and lines count. Metrics condition on no push; 50/50 abstentions, pushes and missing picks stay separate."}


def user_record(rows):
    selected = [row for row in rows if row["userPick"]]
    wins = sum(row["userCorrect"] is True for row in selected)
    losses = sum(row["userCorrect"] is False for row in selected)
    return {"selections": len(selected), "wins": wins, "losses": losses,
            "accuracy": wins / (wins + losses) if wins + losses else None,
            "pushes": sum(row["actualOutcome"] == "Push" for row in selected),
            "pending": sum(row["actualOutcome"] is None for row in selected),
            "reported_after_kickoff": sum(row["userReportedAfterKickoff"] for row in selected)}
