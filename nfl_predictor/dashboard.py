"""Reviewed matchup rows for the portable dashboard and its live score endpoint."""
from datetime import datetime, timezone

from .engine import FeatureEngine
from .features import normalize_team
from .freshness import timestamp
from .storage import clean


def injury_reports(prediction, side):
    """Designated players the forecast saw, so a locked bet can show what was known then."""
    if not prediction:
        return []
    reports = prediction.get("detail", {}).get(side + "_injuries", {}).get("reports", [])
    return [{"name": r["name"], "position": r.get("position"), "status": r["status"]} for r in reports if r.get("name") and r.get("status")]


def week_payload(manifest, metadata, batches, dataset=None, card=None):
    """Only saved pregame picks are displayed; score refresh never makes new picks."""
    now = datetime.now(timezone.utc)
    forecasts, original = {}, {}
    for batch in batches:
        issued = timestamp(batch.get("issued_at") or batch["as_of"] + "T23:59:59+00:00").isoformat()
        for forecast in batch["forecast"]:
            event = str(forecast["espn_id"])
            candidate = {**forecast, "issued_at": batch.get("issued_at") or batch["as_of"], "sort_time": issued}
            if event not in original or issued < original[event]["sort_time"]:
                original[event] = candidate
            if event not in forecasts or issued > forecasts[event]["sort_time"]:
                forecasts[event] = candidate
    engine = FeatureEngine(dataset, metadata) if dataset else None
    schedule = {str(g["espn"]): g for g in dataset["schedule"] if g.get("espn")} if dataset else {}
    rows = []
    for game in manifest["games"]:
        event = str(game["event_id"])
        home, away = normalize_team(game["home"]), normalize_team(game["away"])
        prediction, first = forecasts.get(event), original.get(event)
        if prediction:
            if (prediction["home"], prediction["away"]) != (home, away):
                raise ValueError("Forecast/dashboard team identity conflict")
            issued = prediction["sort_time"]
            if timestamp(issued) >= timestamp(game["kickoff"]):
                raise ValueError("Dashboard cannot display a backdated prediction")
        home_meta, away_meta = metadata["teams"][home], metadata["teams"][away]
        ht, at = {}, {}
        if engine and event in schedule:
            ht, at = engine.travel_state(home, schedule[event]), engine.travel_state(away, schedule[event])
        completed = game.get("completed") is True
        tied = completed and game["home_score"] == game["away_score"]
        first_correct = ((first["home_probability"] >= .5) == (game["home_score"] > game["away_score"])) if completed and not tied and first else None
        source_time = manifest.get("retrieved_at", manifest.get("scoreboard_source", {}).get("retrieved_at"))
        rows.append({
            "eventId": event, "season": manifest["season"], "week": manifest["week"], "kickoff": game["kickoff"],
            "homeCode": home, "awayCode": away, "homeName": home_meta["name"], "awayName": away_meta["name"],
            "homeLogo": "team-logos/" + home_meta["logo_file"], "awayLogo": "team-logos/" + away_meta["logo_file"],
            "homeColor": home_meta.get("color"), "awayColor": away_meta.get("color"),
            "homeScore": game.get("home_score") if completed else game.get("home_live_score") if game.get("state") == "in" else None,
            "awayScore": game.get("away_score") if completed else game.get("away_live_score") if game.get("state") == "in" else None,
            "state": game.get("state", "unknown"), "statusDetail": game.get("status_detail"), "clock": game.get("clock"), "period": game.get("period"),
            "venue": game.get("venue", {}).get("fullName"), "slateEligible": game.get("slate_eligible", True),
            "pick": prediction["pick"] if prediction else None, "homeProbability": prediction["home_probability"] if prediction else None,
            "pickProbability": max(prediction["home_probability"], 1 - prediction["home_probability"]) if prediction else None,
            "predictionStage": prediction.get("stage", "original") if prediction else None,
            "forecastIssuedAt": prediction["issued_at"] if prediction else None,
            "forecastSources": prediction.get("sources", {}) if prediction else {},
            "modelName": prediction.get("model", "v2_original") if prediction else None,
            "shadowComparisons": [{"model": r["model"], "homeProbability": r["home_probability"]}
                                  for r in prediction.get("shadow_forecasts", [])] if prediction else [],
            "eloHomeProbability": prediction.get("elo_home_probability") if prediction else None,
            "marketHomeProbability": prediction.get("market", {}).get("home_probability") if prediction else None,
            "totalProjection": prediction.get("total_projection") if prediction else None,
            "spreadProjection": prediction.get("spread_projection") if prediction else None,
            "originalPick": first["pick"] if first else None, "originalHomeProbability": first["home_probability"] if first else None,
            "originalCorrect": first_correct, "tied": tied,
            "homeClockKickoff": ht.get("home_clock_kickoff"), "awayClockKickoff": at.get("home_clock_kickoff"),
            "homeTimeZoneShift": ht.get("clock_shift"), "awayTimeZoneShift": at.get("clock_shift"),
            "homeTravelKm": ht.get("km"), "awayTravelKm": at.get("km"),
            "homeQb": prediction.get("home_qb", {}).get("name") if prediction else None,
            "awayQb": prediction.get("away_qb", {}).get("name") if prediction else None,
            "homeQbStatus": prediction.get("home_qb_status") if prediction else None,
            "awayQbStatus": prediction.get("away_qb_status") if prediction else None,
            "homeInjuries": injury_reports(prediction, "home"), "awayInjuries": injury_reports(prediction, "away"),
            "weather": prediction.get("detail", {}).get("weather") if prediction else None,
            "updatedAt": source_time,
        })
    rows.sort(key=lambda r: (r["kickoff"], r["eventId"]))
    from .totals import card_rows, total_forecasts
    if card and (card.get("season"), card.get("week")) != (manifest["season"], manifest["week"]):
        raise ValueError("Brochure is for a different season/week")
    brochure_rows = card_rows(card, manifest["games"], total_forecasts(batches))
    season_schedule = {}
    for game in dataset["schedule"] if dataset else []:
        if game["season"] == manifest["season"] and game.get("espn"):
            season_schedule.setdefault(str(game["week"]), []).append({"eventId": str(game["espn"]), "homeCode": game["home_team"], "awayCode": game["away_team"]})
    return {"title": "No Fun League", "generatedAt": manifest["retrieved_at"], "buildStatus": "creating",
            "seasonSchedule": season_schedule,
            "period": {"season": manifest["season"], "week": manifest["week"]},
            "queries": {"brochure": {"rows": clean(brochure_rows), "source": {
                "label": "Three weekly brochure totals", "provider": "User-provided card / ESPN results / experimental totals model",
                "executedAt": manifest["retrieved_at"], "evidenceFlow": [
                    {"title": "Printed lines", "detail": card.get("source") if card else "Awaiting the user's three games and exact printed lines."},
                    {"title": "Your selections", "detail": "User-reported choices are scored separately from model predictions. A report made after kickoff is labeled and never treated as a timestamped model pick."},
                    {"title": "Prediction timing", "detail": "Only a saved pregame total-points projection and a brochure line received before kickoff can count as a prediction. Historical results are not backfilled picks."},
                    {"title": "Settlement", "detail": "Compare final combined score to the printed total. Whole-point pushes stay separate; actual contest terms govern settlement."}]}},
                        "matchups": {"rows": clean(rows), "source": {
                "label": "NFL weekly matchups, scores and saved forecasts", "provider": "ESPN / NFL / No Fun League",
                "executedAt": manifest["retrieved_at"], "url": manifest.get("scoreboard_source", {}).get("url"),
                "evidenceFlow": [
                    {"title": "Scores", "detail": "Public ESPN NFL scoreboard; season and week are validated. Only completed games count toward results."},
                    {"title": "Market totals", "detail": "Timestamped ESPN-listed provider quotes. First observed means the first quote this tracker captured, not the market opening line. Movement compares the same provider. No line is invented for games without a saved quote. Market picks and fixed brochure lines remain separate."},
                    {"title": "Point spreads", "detail": "ESPN-listed provider home spreads, observed before kickoff. An experimental score-margin model estimates cover and push probabilities. The first directional pick is settled at its saved line."},
                    {"title": "Weekly toss-up", "detail": "The saved winner forecast closest to 50%. Before forecasts are available, the smallest current spread is an early market watch."},
                    {"title": "Picks", "detail": "Saved pre-kickoff model snapshots; original picks remain separate from later revisions. Refreshing scores never regenerates predictions."},
                    {"title": "Branding", "detail": "Official team logos retrieved from NFL.com. Team names/colors and venues are checked against ESPN team metadata."},
                    {"title": "Travel", "detail": "Home-clock kickoff uses IANA time zones on the game date and city-level venue coordinates. It is a proxy, not observed acclimation."}],
                "metricDefinitions": [
                    {"label": "Pick probability", "definition": "Estimated chance the selected team wins, conditional on a decisive result. It is not certainty or a guarantee."},
                    {"label": "Original picks record", "definition": "Correct and incorrect original picks among completed, non-tied games in the displayed population. Later forecast revisions do not rewrite this record."}],
                "limitations": ["Score updates depend on provider and hosting refresh. Stale data retain their actual last successful source time.",
                                 "Research features and body-clock effects are experimental. No current causal time-zone penalty is assumed."]}}}}
