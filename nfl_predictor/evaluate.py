"""Separate tuning, family selection and retrospective reporting by season."""

import hashlib
import json

import pandas as pd

from .features import BASE_NAMES, PROTECTION, CONTINUITY, TRANSITION, load_features
from .model import fit, predict, scores

FAMILIES = {
    "efficiency_qb": BASE_NAMES[:11],
    "v2_all": BASE_NAMES,
    "protection": BASE_NAMES + PROTECTION,
    "qb_transition": BASE_NAMES + TRANSITION,
    "ol_continuity": BASE_NAMES + CONTINUITY,
    "combined": BASE_NAMES + PROTECTION + CONTINUITY + TRANSITION,
}


def rolling(frame, season, names, alpha):
    parts = []
    decisive = frame[frame.target.isin([0, 1])]
    for week in sorted(decisive.loc[decisive.season.eq(season), "week"].unique()):
        train = decisive[(decisive.season < season) |
                         (decisive.season.eq(season) & (decisive.week < week))]
        test = decisive[decisive.season.eq(season) & decisive.week.eq(week)]
        model = fit(train, names, alpha)
        result = test[["game_id", "season", "week", "away_team", "home_team", "target"]].copy()
        result["home_probability"] = predict(model, test)
        result["train_last_season"] = int(train.season.max())
        result["train_last_week"] = int(train[train.season.eq(train.season.max())].week.max())
        parts.append(result)
    if not parts:
        raise ValueError("No decisive evaluation games")
    return pd.concat(parts, ignore_index=True)


def evaluate(root, output):
    if output.exists():
        raise FileExistsError("Choose a new report directory; existing reports are immutable")
    frame = load_features(root)
    tuning, selected_alphas, validation = [], {}, []
    for family, names in FAMILIES.items():
        for alpha in (15., 60., 150.):
            result = rolling(frame, 2024, names, alpha)
            tuning.append({"family": family, "alpha": alpha,
                           **scores(result.target, result.home_probability)})
        chosen = min((r for r in tuning if r["family"] == family), key=lambda r: r["brier"])
        selected_alphas[family] = chosen["alpha"]
        result = rolling(frame, 2025, names, chosen["alpha"])
        validation.append({"family": family, "alpha": chosen["alpha"],
                           **scores(result.target, result.home_probability)})
    selected = min(validation, key=lambda r: r["brier"])
    checks, predictions = [], {}
    for family, names in FAMILIES.items():
        result = rolling(frame, 2026, names, selected_alphas[family])
        predictions[family] = result
        checks.append({"family": family, "alpha": selected_alphas[family],
                       **scores(result.target, result.home_probability)})
    # Reproduce the actual v2 penalty, independently of the new tuning policy.
    baseline = rolling(frame, 2026, BASE_NAMES, 60.)
    frozen = json.loads((root / "archive/session-2026-11-10/enhanced/model.json").read_text())
    old = {g["game_id"]: g["p"] for g in frozen["backtest"]}
    max_difference = max(abs(old[g.game_id] - g.home_probability) for g in baseline.itertuples())
    if len(old) != len(baseline) or max_difference > 1e-7:
        raise AssertionError("v2 reproduction failed")
    train = frame[frame.target.isin([0, 1])]
    champion = fit(train, FAMILIES[selected["family"]], selected["alpha"])
    report = {
        "version": "3.0.0", "snapshot_as_of": "2026-11-10",
        "deployment_status": "research_only; existing v2 remains the live baseline",
        "policy": {"penalty_tuning": "rolling 2024", "family_selection": "rolling 2025 Brier",
                   "diagnostic_only": "2026 weeks 1-9; these results were already examined",
                   "prospective_validation": "Only timestamped future, pre-kickoff forecasts qualify"},
        "selected": selected, "tuning_2024": tuning, "selection_2025": validation,
        "diagnostics_2026": checks, "v2_frozen_penalty_2026": scores(baseline.target, baseline.home_probability),
        "v2_max_probability_reproduction_error": max_difference,
        "training_games": len(train), "model": champion,
        "feature_missing_counts": {n: int(frame[n].isna().sum()) for n in FAMILIES["combined"]},
        "input_sha256": {str(p.relative_to(root)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [root / "data/snapshots/history-2026-11-10.json",
                                   root / "archive/session-2026-11-10/enhanced/pregame_features.csv",
                                   root / "archive/session-2026-11-10/enhanced/model.json",
                                   *sorted((root / "archive/session-2026-11-10/enhanced").glob("aggregates_*.json"))]},
        "limitations": frozen["limitations"] + [
            "New candidates were designed after Week 10 losses were seen. Earlier-season selection reduces direct fitting to those losses; it is not a new untouched trial.",
            "QB hits are a public pressure proxy, not complete tracked pressure rates.",
            "OL continuity is overlap of the top five prior-game snap leaders, not a confirmed projected starting line.",
            "QB-coach familiarity measures prior dropbacks with the same head coach, including other teams. It does not establish coordinator or scheme familiarity.",
            "Missing features are train-median imputed with explicit missingness indicators.",
            "The fitted artifact uses frozen November 10 data. Do not use it for new picks without updating team/QB/injury/weather inputs."
        ]}
    output.mkdir(parents=True)
    (output / "evaluation.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    predictions[selected["family"]].to_csv(output / "retrospective-2026.csv", index=False)
    cols = ["game_id", "season", "week", "home_team", "away_team", "target"] + FAMILIES["combined"]
    frame[cols].to_csv(output / "features.csv", index=False)
    return report
