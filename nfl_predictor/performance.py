"""Read-only season scoring of recorded picks, independently of model fitting."""
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import threading
import time
from zoneinfo import ZoneInfo

from .features import normalize_team
from .freshness import timestamp
from .model import scores
from .storage import clean, read_json
from .totals import card_rows, total_forecasts

KINDS = {"winner":"Winner picks", "market":"Market totals", "printed-model":"Printed card model", "printed-user":"Your printed card picks"}


def schedule_index(dataset, season):
    selected = {}
    for game in dataset.get("schedule", []):
        if game.get("season") != season or not game.get("espn"):
            continue
        event = str(game["espn"])
        if event in selected:
            raise ValueError("Duplicate scheduled event")
        kickoff = datetime.fromisoformat(f"{game['gameday']}T{game['gametime']}").replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc).isoformat()
        selected[event] = {"event_id":event,"season":season,"week":game["week"],"home":normalize_team(game["home_team"]),
                           "away":normalize_team(game["away_team"]),"kickoff":kickoff,"completed":False,"state":"unknown",
                           "home_score":None,"away_score":None}
    return selected


def issue_time(batch):
    if batch.get("issued_at"):
        return batch["issued_at"], timestamp(batch["issued_at"]), "exact"
    day = date.fromisoformat(batch["as_of"])
    return day.isoformat(), timestamp(day.isoformat()+"T23:59:59.999999Z"), "date"


def probability(value):
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Invalid saved prediction probability")
    return float(value)


def original_winners(batches, scheduled, batch_sources=()):
    originals, latest, counts = {}, {}, {}
    season = next(iter(scheduled.values()))["season"] if scheduled else None
    for index, batch in enumerate(batches):
        issued, ordered, precision = issue_time(batch)
        seen = set()
        for candidate in batch.get("forecast", []):
            event = str(candidate["espn_id"])
            if event in seen:
                raise ValueError("Duplicate forecast within a batch")
            seen.add(event)
            if event not in scheduled:
                # Other seasons do not enter this season's record.
                candidate_season = batch.get("season") or (int(candidate["game_id"][:4]) if candidate.get("game_id","")[:4].isdigit() else ordered.year)
                if candidate_season == season:
                    raise ValueError("Forecast event is missing from this season's schedule")
                continue
            game = scheduled[event]
            if (normalize_team(candidate["home"]),normalize_team(candidate["away"])) != (game["home"],game["away"]):
                raise ValueError("Forecast/schedule team identity conflict")
            p = probability(candidate["home_probability"])
            if normalize_team(candidate["pick"]) != (game["home"] if p >= .5 else game["away"]):
                raise ValueError("Saved winner pick conflicts with its probability")
            if ordered >= timestamp(game["kickoff"]):
                raise ValueError("Saved forecast does not establish a pregame issue time")
            value = {**candidate,"home":game["home"],"away":game["away"],"pick":normalize_team(candidate["pick"]),
                     "issued":issued,"ordered":ordered,"precision":precision,
                     "source":batch_sources[index] if index < len(batch_sources) else {"label":"Immutable forecast batch"}}
            for mapping, earlier in ((originals,True),(latest,False)):
                if event in mapping and ordered == mapping[event]["ordered"] and p != mapping[event]["home_probability"]:
                    raise ValueError("Conflicting forecasts share an issue timestamp")
                if event not in mapping or (ordered < mapping[event]["ordered"] if earlier else ordered > mapping[event]["ordered"]):
                    mapping[event] = value
            counts.setdefault(event,set()).add(ordered)
    return originals, latest, counts


def result_status(game, pick, kind, line=None):
    if not pick:
        return "no-pick", None, None
    if pick == "Even":
        return "abstained", None, None
    if game.get("state") in {"pre","in"} and not game.get("completed"):
        return "pending", None, None
    if not game.get("completed") or game.get("state") != "post":
        return "unavailable", None, None
    home, away = game.get("home_score"), game.get("away_score")
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x < 0 for x in (home,away)):
        raise ValueError("Completed result is missing valid scores")
    if kind == "winner":
        if home == away:
            return "tie", None, None
        target = int(home > away)
        return "final", pick == (game["home"] if target else game["away"]), target
    total = home + away
    if total == line:
        return "push", None, None
    target = int(total > line)
    return "final", pick == ("Over" if target else "Under"), target


def total_probability(analysis, line):
    if float(analysis["line"]) != float(line):
        raise ValueError("Saved total analysis differs from its tracked line")
    over, under, push = [probability(analysis[key]) for key in ("over_probability","under_probability","push_probability")]
    if abs(over + under + push - 1) > 1e-6 or over + under <= 0:
        raise ValueError("Invalid saved total probability distribution")
    lean = analysis["lean"]
    if lean not in {"Over","Under","Even"} or (lean == "Over" and over <= under) or (lean == "Under" and under <= over) or (lean == "Even" and over != under):
        raise ValueError("Saved total direction conflicts with its probabilities")
    return over / (over + under)


def summary(rows, kind):
    decided = [r for r in rows if r["status"] == "final"]
    probabilistic = [r for r in decided if r["scoringProbability"] is not None]
    metric = scores([r["target"] for r in probabilistic],[r["scoringProbability"] for r in probabilistic])
    wins = sum(r["correct"] is True for r in decided)
    return {"kind":kind,"label":KINDS[kind],"recorded":sum(r["pick"] not in {None,"Even"} for r in rows),
            "decided":len(decided),"wins":wins,"losses":len(decided)-wins,"accuracy":wins/len(decided) if decided else None,
            "brier":metric["brier"],"logLoss":metric["log_loss"],"probabilityGames":metric["games"],
            "pending":sum(r["status"]=="pending" for r in rows),"unavailable":sum(r["status"]=="unavailable" for r in rows),
            "ties":sum(r["status"]=="tie" for r in rows),"pushes":sum(r["status"]=="push" for r in rows),
            "noPick":sum(r["status"]=="no-pick" for r in rows),"abstained":sum(r["status"]=="abstained" for r in rows),
            "reportedLate":sum(r.get("reportedAfterKickoff") is True for r in rows)}


def season_payload(dataset, season, batches, observations, cards, results, batch_sources=(), warnings=()):
    scheduled = schedule_index(dataset,season)
    games = dict(scheduled)
    seen_results = set()
    for week, manifest in results.items():
        if (manifest["season"],manifest["week"]) != (season,week):
            raise ValueError("Results are for a different season/week")
        for game in manifest["games"]:
            event = str(game["event_id"])
            if event in seen_results:
                raise ValueError("Duplicate performance result")
            seen_results.add(event)
            expected = scheduled.get(event)
            if not expected or expected["week"] != week or (normalize_team(game["home"]),normalize_team(game["away"])) != (expected["home"],expected["away"]):
                raise ValueError("Performance result identity conflict")
            games[event] = {**game,"season":season,"week":week,"home":expected["home"],"away":expected["away"]}
    originals, latest, counts = original_winners(batches,games,batch_sources)
    rows = []
    def append(game, kind, pick, issued, p=None, line=None, **extra):
        status, correct, target = result_status(game,pick,kind,line)
        confidence = (p if (pick == game["home"] if kind == "winner" else pick == "Over") else 1-p) if p is not None and pick not in {None,"Even"} else None
        manifest = results.get(game["week"],{})
        rows.append({"selectionId":f"{season}:{game['week']}:{game['event_id']}:{kind}","season":season,"week":game["week"],
                     "kind":kind,"eventId":game["event_id"],"home":game["home"],"away":game["away"],"kickoff":game["kickoff"],
                     "pick":pick,"issuedAt":issued,"line":line,"probability":confidence,"scoringProbability":p,"target":target,
                     "status":status,"correct":correct,"homeScore":game.get("home_score") if game.get("completed") else None,
                     "awayScore":game.get("away_score") if game.get("completed") else None,
                     "resultSource":manifest.get("scoreboard_source"),"resultRetrievedAt":manifest.get("retrieved_at"),**extra})
    for event, first in originals.items():
        recent = latest[event]
        append(games[event],"winner",first["pick"],first["issued"],first["home_probability"],
               issuePrecision=first["precision"],forecastSource=first["source"],model=first.get("model","v2_original"),
               revisionCount=max(0,len(counts[event])-1),latestPick=recent["pick"],latestIssuedAt=recent["issued"],
               latestProbability=max(recent["home_probability"],1-recent["home_probability"]))
    seen_market = set()
    for item in observations:
        if item["season"] != season:
            continue
        event = str(item["event"])
        game = games[event]
        if event in seen_market or item["week"] != game["week"] or (item["home"],item["away"]) != (game["home"],game["away"]):
            raise ValueError("Original market selection identity conflict")
        seen_market.add(event)
        line = float(item["line"])
        if not math.isfinite(line) or not 0 < line < 150 or not (line*2).is_integer():
            raise ValueError("Invalid tracked market total")
        observed = timestamp(item["observed_at"])
        if observed >= timestamp(game["kickoff"]):
            raise ValueError("Market quote was captured after kickoff")
        analysis = json.loads(item["analysis"]) if item["analysis"] else None
        p = total_probability(analysis,line) if analysis else None
        if analysis and not timestamp(item["forecast_issued_at"]) <= observed:
            raise ValueError("Total projection was unavailable when its line was captured")
        append(game,"market",analysis["lean"] if analysis else None,item["observed_at"] if analysis else None,p,line,
               provider=item["book"],providerId=item["book_id"],forecastIssuedAt=item["forecast_issued_at"],
               quoteSource={"url":item["url"],"sha256":item["source_sha256"],"retrieved_at":item["observed_at"]})
    printed_forecasts = total_forecasts(batches)
    for card in cards:
        if card["season"] != season:
            continue
        for item in card_rows(card,[g for g in games.values() if g["week"]==card["week"]],printed_forecasts):
            game = games[item["eventId"]]
            # A timely projection is not evidence that an exact-line choice was saved.
            forecast = printed_forecasts.get(item["eventId"],{})
            analysis = item["analysis"] if forecast.get("total_pick") else None
            append(game,"printed-model",analysis["lean"] if analysis else None,item["forecastIssuedAt"] if analysis else None,
                   total_probability(analysis,item["line"]) if analysis else None,item["line"],cardSource=card.get("source"))
            append(game,"printed-user",item["userPick"],item["userReportedAt"],line=item["line"],
                   reportedAfterKickoff=item["userReportedAfterKickoff"],cardSource=card.get("source"))
    if len({r["selectionId"] for r in rows}) != len(rows):
        raise ValueError("Duplicate recorded selection")
    rows.sort(key=lambda r:(r["week"],r["kickoff"],r["selectionId"]))
    summaries = [summary([r for r in rows if r["kind"]==kind],kind) for kind in KINDS]
    weekly, calibration = [], []
    for kind in KINDS:
        for week in range(1,19):
            group = [r for r in rows if r["kind"]==kind and r["week"]==week]
            weekly.append({**summary(group,kind),"week":week,"weekLabel":f"Week {week}",
                           "scheduledGames":sum(g["week"]==week for g in scheduled.values()),
                           "accuracyPct":100*sum(r["correct"] is True for r in group)/sum(r["status"]=="final" for r in group) if any(r["status"]=="final" for r in group) else None})
        for week in (None,*range(1,19)):
            for low,high in ((.5,.6),(.6,.7),(.7,.8),(.8,1.000001)):
                group = [r for r in rows if r["kind"]==kind and (week is None or r["week"]==week) and r["status"]=="final" and r["probability"] is not None and low <= r["probability"] < high]
                calibration.append({"kind":kind,"week":week,"lower":low,"upper":min(high,1.),"games":len(group),
                                    "band":f"{low:.0%}–{min(high,1.):.0%} (n={len(group)})",
                                    "meanConfidence":100*sum(r["probability"] for r in group)/len(group) if group else None,
                                    "hitRate":100*sum(r["correct"] is True for r in group)/len(group) if group else None})
    sources = [manifest["scoreboard_source"] for manifest in results.values() if manifest.get("scoreboard_source")]
    times = [manifest["retrieved_at"] for manifest in results.values() if manifest.get("retrieved_at")]
    source = {"label":"Recorded season picks and validated final scores","provider":"Immutable forecasts / tracked market quotes / supplied cards / ESPN",
              "executedAt":min(times,key=timestamp) if times else None,"scope":f"{season} regular season; recorded picks only",
              "sources":sources,"warnings":list(warnings),"evidenceFlow":[
                  {"title":"Original record","detail":"One earliest saved winner forecast or first tracked directional market pick per game. Later revisions do not rewrite this record."},
                  {"title":"Exact totals","detail":"Grade against the original provider and total. Printed card selections and user-reported choices remain separate."},
                  {"title":"Probability scoring","detail":"Brier score and log loss use decisive outcomes only. Total probabilities condition on no push. User choices have no recorded probabilities."},
                  {"title":"Coverage","detail":"Weeks without recorded picks have no accuracy, rather than zero accuracy. Historical backtests never enter this record. Date-only legacy issue times retain their precision."}]}
    return clean({"season":season,"generatedAt":datetime.now(timezone.utc).isoformat(),"warnings":list(warnings),"resultSources":sources,
                  "queries":{name:{"rows":values,"source":{**source,"label":label}} for name,values,label in (
                      ("performance-picks",rows,"Recorded season selections"),("performance-summary",summaries,"Season pick metrics"),
                      ("performance-weeks",weekly,"Weekly pick metrics"),("performance-calibration",calibration,"Confidence calibration"))}})


class SeasonPerformance:
    """Cache validated results without calling quote enrichment or fitting models."""
    def __init__(self, manager, ttl=60):
        self.manager, self.ttl = manager, ttl
        self.lock, self.cached, self.updated = threading.Lock(), None, 0.
        self.results = {}

    def get(self):
        with self.lock:
            if self.cached is not None and time.monotonic()-self.updated < self.ttl:
                return self.cached
            from .server import fetch_week
            with self.manager.lock:
                dataset, batches = self.manager.dataset, list(self.manager.batches)
                batch_sources = list(self.manager.batch_sources)
            scheduled = schedule_index(dataset,self.manager.season)
            originals, _, _ = original_winners(batches,scheduled,batch_sources)
            observations = self.manager.line_tracker.original_selections(self.manager.season)
            directory = self.manager.card_path.parent if self.manager.card_path else Path("data/cards")
            cards = [read_json(path) for path in sorted(directory.glob(f"{self.manager.season}-week*.json"))]
            weeks = {scheduled[e]["week"] for e in originals} | {r["week"] for r in observations} | {c["week"] for c in cards}
            results, warnings = {}, []
            now = datetime.now(timezone.utc)
            for week in sorted(weeks):
                previous = self.results.get(week)
                cache_age = (now-timestamp(previous["retrieved_at"])).total_seconds() if previous else math.inf
                lifetime = 3600 if previous and all(g["completed"] for g in previous["games"]) else 60
                try:
                    if previous and 0 <= cache_age < lifetime:
                        results[week] = previous
                        continue
                    manifest = fetch_week(self.manager.season,week)
                    expected = {event:(g["home"],g["away"]) for event,g in scheduled.items() if g["week"]==week}
                    actual = {str(g["event_id"]):(normalize_team(g["home"]),normalize_team(g["away"])) for g in manifest["games"]}
                    if not expected or expected != actual or len(actual) != len(manifest["games"]):
                        raise ValueError("Incomplete or conflicting result slate")
                    self.results[week] = results[week] = manifest
                except Exception:
                    if previous:
                        results[week] = previous
                    warnings.append(f"Week {week}: result provider unavailable; {'retaining the earlier source time' if previous else 'results remain unavailable'}.")
            self.cached = season_payload(dataset,self.manager.season,batches,observations,cards,results,batch_sources,warnings)
            self.updated = time.monotonic()
            return self.cached
