"""Grade primary/shadow/benchmark forecasts on explicitly matched games."""
import numpy as np

from .freshness import timestamp
from .market import aligned_consensus
from .model import scores


def score_experiments(batch, results):
    by_id = {str(g["event_id"]): g for g in results["games"]}
    models, primary = {}, {}
    for forecast in batch["forecast"]:
        event = str(forecast["espn_id"])
        game = by_id.get(event)
        if not game or not game.get("completed") or game["home_score"] == game["away_score"]:
            continue
        if not batch.get("issued_at") or timestamp(batch["issued_at"]) >= timestamp(game["kickoff"]):
            raise ValueError("Experiments require an exact, pre-kickoff issue time")
        if (forecast["home"], forecast["away"]) != (game["home"], game["away"]):
            raise ValueError("Experiment game identity mismatch")
        target = int(game["home_score"] > game["away_score"])
        primary[event] = (target, forecast["home_probability"])
        values = [(item["model"], item["home_probability"]) for item in forecast.get("shadow_forecasts", [])]
        if forecast.get("elo_home_probability") is not None:
            values.append(("independent_elo", forecast["elo_home_probability"]))
        market = forecast.get("market", {})
        if market.get("status") == "ok":
            quotes = market.get("quotes", [])
            if any(str(q.get("event_id")) != event for q in quotes):
                raise ValueError("Market quote belongs to a different event")
            aligned = aligned_consensus(quotes, batch["issued_at"], game["kickoff"])
            if aligned["status"] == "ok":
                values.append(("time_aligned_market", aligned["home_probability"]))
        for name, probability in values:
            if event in models.setdefault(name, {}):
                raise ValueError("Duplicate experiment prediction")
            if probability is None or not np.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError("Invalid experiment probability")
            models[name][event] = (target, probability)
    output = []
    for name, rows in models.items():
        ids = sorted(rows)
        y = np.array([rows[key][0] for key in ids])
        p = np.array([rows[key][1] for key in ids])
        base = np.array([primary[key][1] for key in ids])
        output.append({"model": name, **scores(y, p), "primary_same_games": scores(y, base),
                       "delta_brier": float(np.mean((p - y) ** 2 - (base - y) ** 2)),
                       "coverage": f"{len(ids)} of {len(primary)} decisive primary forecasts", "game_ids": ids})
    return {"issued_at": batch.get("issued_at"), "models": output,
            "policy": "Each comparison uses the exact same games. Missing market/shadow predictions are excluded, not scored as losses."}
