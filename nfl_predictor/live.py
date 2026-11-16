"""Rebuild pregame features from current sources, with release checks and lineage."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
from pathlib import Path
import re
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .engine import FeatureEngine, OUT, position_group
from .features import normalize_team
from .freshness import check_pregame, timestamp
from .sources import refresh
from .storage import read_json, sha256, write_new


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tokens, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.tokens.append(" ".join(data.split()))


def parse_staff(html, seed):
    page = PageText()
    page.feed(html)
    result, evidence = {}, {}
    roles = {"head_coach": "Head Coach", "offensive_coordinator": "Offensive Coordinator", "defensive_coordinator": "Defensive Coordinator"}
    for field, role in roles.items():
        candidates = []
        for index, token in enumerate(page.tokens):
            if token.casefold() == role.casefold() or token.casefold().startswith(role.casefold() + "/") or token.casefold().startswith(role.casefold() + " /"):
                nearby = page.tokens[max(0, index - 2): index + 3]
                expected = seed.get(field)
                for text in nearby:
                    if expected and text.casefold() == expected.casefold():
                        candidates.insert(0, text)
                for offset in (-1, 1):
                    if 0 <= index + offset < len(page.tokens):
                        name = page.tokens[index + offset]
                        if 2 <= len(name.split()) <= 4 and len(name) <= 50 and not any(word in name.casefold() for word in ("coach", "coordinator", "experience", "season", "staff", "assistant", "football", "bio", "more", "view")):
                            candidates.append(name)
        result[field] = candidates[0] if candidates else None
        evidence[field] = "matched official role/name adjacency" if candidates else "not resolved"
    result["role_evidence"] = evidence
    return result


def collect_staff(seed, destination):
    url = seed["source"]
    with urlopen(Request(url, headers={"User-Agent": "NoFunLeaguePredictor/4.0"}), timeout=30) as response:
        content = response.read()
    destination.write_bytes(content)
    parsed = parse_staff(content.decode("utf-8", errors="replace"), seed)
    return parsed, {"url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "status": "ok" if all(parsed.get(k) for k in ("head_coach", "offensive_coordinator", "defensive_coordinator")) else "unverified"}


def team_context(engine, code, depth, summary, now):
    injuries, slots = {}, []
    def remember(athlete, injury, position=None):
        player_id = str(athlete.get("id", ""))
        date = injury.get("date")
        if date and timestamp(date) > now:
            return
        row = {"espn_id": player_id, "pid": engine.espn_ids.get(player_id),
               "name": athlete.get("displayName"), "position": position or athlete.get("position", {}).get("abbreviation"),
               "status": injury.get("status"), "updated_at": date}
        previous = injuries.get(player_id)
        if previous is None or (date or "") >= (previous.get("updated_at") or ""):
            injuries[player_id] = row
    for group in depth.get("depthchart", []):
        for position, entry in group.get("positions", {}).items():
            athletes = entry.get("athletes", [])
            slots.append({"position": position.upper(), "athletes": athletes})
            for athlete in athletes:
                for injury in athlete.get("injuries", []):
                    remember(athlete, injury, position.upper())
    for group in summary.get("injuries", []):
        if normalize_team(group.get("team", {}).get("abbreviation")) == code:
            for injury in group.get("injuries", []):
                remember(injury.get("athlete", {}), injury)
    for slot in slots:
        healthy = [a for a in slot["athletes"] if injuries.get(str(a["id"]), {}).get("status") not in OUT]
        for athlete in slot["athletes"]:
            row = injuries.get(str(athlete["id"]))
            if row and row.get("status") in OUT and healthy:
                row["replacement_pid"] = engine.espn_ids.get(str(healthy[0]["id"]))
    candidates = [a for slot in slots if slot["position"] == "QB" for a in slot["athletes"]
                  if injuries.get(str(a["id"]), {}).get("status") not in OUT]
    if not candidates:
        raise ValueError("No available projected QB: " + code)
    def pid(athlete):
        return engine.espn_ids.get(str(athlete["id"])) or "ESPN:" + str(athlete["id"])
    result = {"qb_id": pid(candidates[0]), "qb_name": candidates[0]["displayName"],
              "qb_status": injuries.get(str(candidates[0]["id"]), {}).get("status", "No current designation reported"),
              "backup_qb_id": pid(candidates[1]) if len(candidates) > 1 else None,
              "backup_qb_name": candidates[1]["displayName"] if len(candidates) > 1 else None,
              "injuries": list(injuries.values()), "projected_lineup": [
                  {"position": slot["position"], "pid": pid(available[0]), "name": available[0]["displayName"]}
                  for slot in slots if (available := [a for a in slot["athletes"] if injuries.get(str(a["id"]), {}).get("status") not in OUT])],
              "qb_identity_mapped": pid(candidates[0]) in engine.players}
    kickers = [athlete for slot in slots if slot["position"] in {"K", "PK"} for athlete in slot["athletes"]
               if injuries.get(str(athlete["id"]), {}).get("status") not in OUT]
    result["kicker_id"] = pid(kickers[0]) if kickers else None
    result["kicker_name"] = kickers[0]["displayName"] if kickers else None
    return result


def coverage(engine, season, week):
    expected = [g for g in engine.schedule.values() if g["season"] == season and g["week"] < week]
    missing = [g["game_id"] for g in expected if g.get("home_score") is None or
               (g["game_id"], g["home_team"]) not in engine.team_by_game or
               (g["game_id"], g["away_team"]) not in engine.team_by_game]
    return {"expected_games": len(expected), "missing_games": missing, "complete": not missing and (bool(expected) or week == 1)}


def prepare(dataset_path, venues_path, staff_seed_path, season, week, output, review_path=None, event_ids=None):
    output = Path(output)
    dataset, venues = read_json(dataset_path), read_json(venues_path)
    engine = FeatureEngine(dataset, venues)
    seeds = {row["team"]: row for row in read_json(staff_seed_path)["staff"]}
    reviewed = read_json(review_path) if review_path else {}
    manifest = refresh(season, week, output) if event_ids is None else refresh(season, week, output, event_ids=event_ids)
    now = datetime.now(timezone.utc)
    complete = coverage(engine, season, week)
    source_receipts = [r for r in dataset["sources"] if r["file"] == f"pbp_{season}.csv.gz"]
    stats_receipt = source_receipts[-1] if source_receipts else None
    schedule_by_espn = {g["espn"]: g for g in dataset["schedule"] if g.get("espn")}
    prepared = []
    for game in manifest["games"]:
        if game["state"] != "pre" or timestamp(game["kickoff"]) <= now:
            continue
        if event_ids is not None and str(game["event_id"]) not in event_ids:
            continue
        game["home"], game["away"] = normalize_team(game["home"]), normalize_team(game["away"])
        event = game["event_id"]
        try:
            scheduled = schedule_by_espn.get(event)
            if not scheduled or (scheduled["home_team"], scheduled["away_team"]) != (game["home"], game["away"]):
                raise ValueError("No unambiguous schedule/team match")
            if scheduled.get("home_score") is not None:
                raise ValueError("Schedule already reports this game completed")
            summary = read_json(output / f"summary-{event}.json")
            context = {"teams": {}, "weather": game["sources"].get("weather", {})}
            staff_sources = []
            for side in ("home", "away"):
                code = game[side]
                depth = read_json(output / f"depth-{event}-{side}.json")
                current = team_context(engine, code, depth, summary, now)
                try:
                    staff, receipt = collect_staff(seeds[code], output / f"staff-{code}.html")
                    current["staff"] = staff
                    staff_sources.append(receipt)
                except Exception as exc:
                    staff_sources.append({"status": "error", "error": str(exc)})
                context["teams"][code] = current
            if all(s["status"] == "ok" for s in staff_sources):
                game["sources"]["staff"] = {**staff_sources[0], "event_id": event, "both_teams": staff_sources}
            else:
                game["sources"]["staff"] = {"status": "unverified", "both_teams": staff_sources}
            if stats_receipt:
                game["sources"]["stats"] = {**stats_receipt, "event_id": event, "season": season, "through_week": week - 1,
                    "dataset_sha256": sha256(dataset_path), "coverage": complete,
                    "status": "ok" if complete["complete"] else "incomplete"}
            override = reviewed.get("games", {}).get(event, {})
            for code, changes in override.get("teams", {}).items():
                if code not in context["teams"]:
                    raise ValueError("Review override targets a different team")
                allowed = {k: v for k, v in changes.items() if k in {"qb_id", "qb_name", "backup_qb_id", "backup_qb_name", "injuries", "staff"}}
                context["teams"][code].update(allowed)
            for kind in ("staff", "inactives", "weather"):
                if kind in override.get("sources", {}):
                    game["sources"][kind] = override["sources"][kind]
            if "weather" in override.get("sources", {}):
                context["weather"] = game["sources"]["weather"]
            # Fixed domes are distinguished from retractable roofs. An indoor
            # label alone does not confirm a retractable-roof decision.
            roof_history = {engine.schedule[r["game_id"]].get("roof") for r in engine.history(game["home"], season, week)
                            if engine.schedule[r["game_id"]].get("stadium_id") == scheduled.get("stadium_id")}
            if game.get("venue", {}).get("indoor") is True and roof_history == {"dome"} and scheduled.get("location") != "Neutral":
                weather = game["sources"].get("weather", {})
                if weather.get("status") != "ok":
                    weather = {**game["sources"]["injuries"], "event_id": event}
                weather.update(enclosed_verified=True, roof_evidence="ESPN indoor venue and fixed-dome historical stadium classification")
                game["sources"]["weather"] = context["weather"] = weather
            elif any(roof in roof_history for roof in ("open", "closed")):
                weather = game["sources"].get("weather", {})
                weather["roof_uncertain"] = not (weather.get("roof_decision_verified") is True)
                game["sources"]["weather"] = context["weather"] = weather
            kickoff_local = timestamp(game["kickoff"]).astimezone(ZoneInfo("America/New_York"))
            scheduled = {**scheduled, "gameday": kickoff_local.date().isoformat(), "gametime": kickoff_local.strftime("%H:%M")}
            now = datetime.now(timezone.utc)
            features, detail = engine.features(scheduled, context)
            prepared.append({"event_id": event, "game_id": scheduled["game_id"], "game": game, "schedule": scheduled,
                             "context": context, "features": features, "detail": detail, "preflight": check_pregame(game, now),
                             "feature_built_at": now.isoformat(), "dataset_sha256": sha256(dataset_path)})
        except Exception as exc:
            prepared.append({"event_id": event, "game": game, "preflight": {"ready": False, "reasons": [str(exc)]}})
    result = {"version": "4.0.0", "prepared_at": now.isoformat(), "season": season, "week": week,
              "dataset_sha256": sha256(dataset_path), "venues_sha256": sha256(venues_path),
              "review_sha256": sha256(review_path) if review_path else None, "games": prepared,
              "scoreboard": manifest, "statistics_coverage": complete}
    write_new(output / "prepared.json", result)
    write_new(output / "reviewed-manifest.json", manifest)
    return result
