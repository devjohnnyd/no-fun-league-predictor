"""Score immutable forecast batches; ties and pending games have separate counts."""

from .freshness import timestamp
from .model import scores


def score_batch(forecast_snapshot, scoreboard):
    forecasts = forecast_snapshot["forecast"]
    results = {str(g["event_id"]): g for g in scoreboard["games"]}
    if len(results) != len(scoreboard["games"]):
        raise ValueError("Duplicate game results")
    issued = forecast_snapshot["as_of"]
    # The original snapshot has a calendar date, so its precision is retained.
    # New forecasts must always carry an offset-aware exact issued_at timestamp.
    issued_at = forecast_snapshot.get("issued_at")
    rows, y, p = [], [], []
    seen = set()
    for f in forecasts:
        key = str(f["espn_id"])
        if key in seen:
            raise ValueError("Duplicate forecast")
        seen.add(key)
        probability = f["home_probability"]
        if not isinstance(probability, (int, float)) or not 0 <= probability <= 1:
            raise ValueError("Invalid forecast probability")
        if f["pick"] != (f["home"] if probability >= .5 else f["away"]):
            raise ValueError("Pick conflicts with its probability")
        result = results.get(key)
        row = {"event_id": key, "away": f["away"], "home": f["home"],
               "pick": f["pick"], "home_probability": f["home_probability"]}
        if not result:
            row["status"] = "unavailable"
        else:
            if (result["home"], result["away"]) != (f["home"], f["away"]):
                raise ValueError("Result team mismatch")
            if issued_at and timestamp(issued_at) >= timestamp(result["kickoff"]):
                raise ValueError("Forecast was issued at or after kickoff")
            elif not issued_at and issued >= result["kickoff"][:10]:
                raise ValueError("Date-only forecast cannot establish a pregame issue time")
            if not result["completed"]:
                row["status"] = "pending"
            elif result["home_score"] == result["away_score"]:
                row["status"] = "tie"
            else:
                target = int(result["home_score"] > result["away_score"])
                row.update(status="final", home_score=result["home_score"], away_score=result["away_score"],
                           correct=(f["home_probability"] >= .5) == bool(target))
                y.append(target)
                p.append(f["home_probability"])
        rows.append(row)
    calibration = []
    finals = [r for r in rows if r["status"] == "final"]
    for low, high in ((.5, .6), (.6, .7), (.7, .8), (.8, 1.000001)):
        group = [r for r in finals if low <= max(r["home_probability"], 1 - r["home_probability"]) < high]
        calibration.append({"pick_probability_min": low, "pick_probability_max": min(high, 1.),
            "games": len(group), "correct": sum(r["correct"] for r in group),
            "mean_pick_probability": sum(max(r["home_probability"], 1 - r["home_probability"]) for r in group) / len(group) if group else None})
    return {"forecast_as_of": issued, "results_retrieved_at": scoreboard["retrieved_at"],
            "metrics": scores(y, p), "ties": sum(r["status"] == "tie" for r in rows),
            "pending": sum(r["status"] == "pending" for r in rows),
            "unavailable": sum(r["status"] == "unavailable" for r in rows),
            "expected_losses_in_completed_games": sum(1 - max(v, 1 - v) for v in p),
            "calibration": calibration, "games": rows,
            "results_source": scoreboard.get("scoreboard_source")}
