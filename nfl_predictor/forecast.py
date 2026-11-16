"""Release only pregame forecasts and separately labeled research shadows."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .engine import FeatureEngine
from .freshness import check_pregame, timestamp
from .market import aligned_consensus, csv_quotes, elo_probability, espn_quotes
from .model import design
from .research import model_probabilities
from .sources import ESPN, fetch_json, games_from_scoreboard
from .storage import clean, read_json, sha256, write_new


def contributions(artifact, frame):
    model = artifact["model"]
    matrix, *_ = design(frame, model["names"], model["medians"], model["mean"], model["scale"])
    effects = matrix[0, 1:] * np.asarray(model["beta"])[1:]
    names = model["names"] + [n + "_missing" for n in model["names"]]
    return sorted([{"feature": name, "log_odds_home": float(effect)} for name, effect in zip(names, effects)],
                  key=lambda r: abs(r["log_odds_home"]), reverse=True)[:6]


def issue(dataset_path, venues_path, research_path, prepared_path, output, final=False, now=None, verify_live=True, market_path=None, totals_model_path=None):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    prepared_path = Path(prepared_path)
    prepared, report = read_json(prepared_path), read_json(research_path)
    if sha256(dataset_path) != prepared["dataset_sha256"] or sha256(dataset_path) != report["source_sha256"]["dataset"]:
        raise ValueError("Dataset differs between model and prepared features")
    if sha256(venues_path) != prepared["venues_sha256"] or sha256(venues_path) != report["source_sha256"]["venues"]:
        raise ValueError("Venue metadata differs between model and prepared features")
    now = now or datetime.now(timezone.utc)
    imported_quotes = csv_quotes(market_path) if market_path else []
    totals_model = read_json(totals_model_path) if totals_model_path else None
    if totals_model and (totals_model["source_sha256"] != report["source_sha256"] or
                         totals_model["training_cutoff"] != {"season": prepared["season"], "before_week": prepared["week"]}):
        raise ValueError("Totals model dataset, venues or cutoff differ from the prepared forecast")
    engine = FeatureEngine(read_json(dataset_path), read_json(venues_path))
    current_games = {}
    live_receipt = None
    output.mkdir(parents=True)
    if verify_live:
        url = f"{ESPN}/scoreboard?dates={prepared['season']}&seasontype=2&week={prepared['week']}&limit=1000"
        live, live_receipt = fetch_json(url, output / "issue-scoreboard.json")
        if live.get("season", {}).get("year") != prepared["season"] or live.get("week", {}).get("number") != prepared["week"]:
            raise ValueError("Issue-time scoreboard scope mismatch")
        current_games = {g["event_id"]: g for g in games_from_scoreboard(live)}
        now = datetime.now(timezone.utc)
    forecasts, blocked = [], []
    for entry in prepared["games"]:
        game = dict(entry["game"])
        event = entry["event_id"]
        reasons = []
        if "features" not in entry:
            blocked.append({"event_id": event, "reasons": entry["preflight"]["reasons"]})
            continue
        if verify_live:
            current = current_games.get(event)
            if not current or (current["home"], current["away"]) != (game["home"], game["away"]):
                reasons.append("Issue-time game identity missing or changed")
            else:
                game.update(state=current["state"], kickoff=current["kickoff"])
                if timestamp(current["kickoff"]) != timestamp(entry["game"]["kickoff"]):
                    reasons.append("Kickoff changed; prepare features again")
        preflight = check_pregame(game, now, final)
        reasons.extend(preflight["reasons"])
        age = (now - timestamp(entry["feature_built_at"])).total_seconds()
        if not 0 <= age <= (600 if final else 1800):
            reasons.append("Prepared feature vector is future-dated or too old; rebuild it")
        if not prepared["statistics_coverage"]["complete"]:
            reasons.append("Previous-week statistics are incomplete")
        if final and game["sources"].get("weather", {}).get("roof_uncertain"):
            reasons.append("Final roof decision is not verified")
        model = report["models"]["v2_baseline"]
        if model["training_cutoff"] != {"season": prepared["season"], "before_week": prepared["week"]}:
            reasons.append("Model cutoff differs from the forecast week")
        if reasons:
            blocked.append({"event_id": event, "reasons": reasons})
            continue
        features, detail = engine.features(entry["schedule"], entry["context"])
        if clean(features) != clean(entry["features"]):
            blocked.append({"event_id": event, "reasons": ["Rebuilt features differ from the prepared snapshot"]})
            continue
        frame = pd.DataFrame([features])
        p = float(model_probabilities(model, frame)[0])
        scenarios = []
        for name, scenario in [("Home backup QB", "home_backup"), ("Away backup QB", "away_backup"),
                               ("Questionable players unavailable", "questionable_out"), ("Roof open", "roof_open"), ("Roof closed", "roof_closed")]:
            try:
                values, _ = engine.features(entry["schedule"], entry["context"], scenario)
                probability = float(model_probabilities(model, pd.DataFrame([values]))[0])
                scenarios.append({"name": name, "home_probability": probability, "meaning": "Conditional sensitivity scenario, not a confidence interval"})
            except ValueError as error:
                scenarios.append({"name": name, "home_probability": None, "reason": str(error)})
        shadows = [{"model": name, "home_probability": float(model_probabilities(candidate, frame)[0]), "status": "experimental shadow"}
                   for name, candidate in report["models"].items() if name != "v2_baseline"]
        summary = read_json(prepared_path.parent / f"summary-{event}.json")
        quotes = espn_quotes(summary, game, game["sources"]["injuries"])
        quotes += [row for row in imported_quotes if str(row["event_id"]) == str(event)]
        forecasts.append({"game_id": entry["game_id"], "espn_id": event, "home": game["home"], "away": game["away"],
                          "kickoff": game["kickoff"], "pick": game["home"] if p >= .5 else game["away"],
                          "home_probability": p, "pick_probability": max(p, 1 - p), "stage": "final" if final else "preliminary",
                          "model": "v4_baseline_rebuilt", "home_qb": detail["home_qb"], "away_qb": detail["away_qb"],
                          "home_qb_status": entry["context"]["teams"][game["home"]]["qb_status"],
                          "away_qb_status": entry["context"]["teams"][game["away"]]["qb_status"],
                          "features": features, "detail": detail, "drivers": contributions(model, frame), "scenarios": scenarios,
                          "shadow_forecasts": shadows, "elo_home_probability": elo_probability(engine.dataset, entry["schedule"]),
                          "market": aligned_consensus(quotes, now.isoformat(), game["kickoff"]), "sources": game["sources"], "preflight": preflight})
        if totals_model:
            from .totals import projection, total_features
            forecasts[-1]["total_projection"] = projection(totals_model, total_features(engine, entry["schedule"], entry["context"], detail))
    released_at = now if not verify_live else datetime.now(timezone.utc)
    still_pregame = []
    for forecast in forecasts:
        if timestamp(forecast["kickoff"]) <= released_at:
            blocked.append({"event_id": forecast["espn_id"], "reasons": ["Kickoff passed while calculating the forecast"]})
        else:
            forecast["market"] = aligned_consensus(forecast["market"].get("quotes", []), released_at.isoformat(), forecast["kickoff"])
            still_pregame.append(forecast)
    forecasts = still_pregame
    result = {"version": "4.0.0", "as_of": released_at.date().isoformat(), "issued_at": released_at.isoformat(),
              "season": prepared["season"], "week": prepared["week"], "forecast": forecasts, "blocked": blocked,
              "model_sha256": sha256(research_path), "dataset_sha256": sha256(dataset_path),
              "prepared_sha256": sha256(prepared_path), "issue_time_source": live_receipt,
              "market_import_sha256": sha256(market_path) if market_path else None,
              "totals_model_sha256": sha256(totals_model_path) if totals_model_path else None,
              "attribution": engine.dataset["attribution"], "scenario_policy": "Conditional sensitivities; no arbitrary probabilities assigned to questionable availability"}
    # A draft with zero released predictions must never masquerade as a batch.
    write_new(output / ("forecast.json" if forecasts else "blocked.json"), result)
    return result
