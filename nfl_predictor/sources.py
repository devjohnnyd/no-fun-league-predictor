"""Bounded public API fetches with exact bytes, checksums and retrieval times."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError
import unicodedata

from .freshness import timestamp

ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
STATES = dict(item.split(":") for item in (
    "AZ:Arizona|CA:California|CO:Colorado|DC:District of Columbia|FL:Florida|GA:Georgia|"
    "IL:Illinois|IN:Indiana|LA:Louisiana|MA:Massachusetts|MD:Maryland|MI:Michigan|"
    "MN:Minnesota|MO:Missouri|NC:North Carolina|NJ:New Jersey|NV:Nevada|NY:New York|"
    "OH:Ohio|PA:Pennsylvania|TN:Tennessee|TX:Texas|WA:Washington|WI:Wisconsin"
).split("|"))


def unique_venue_city(venue, geocoding):
    """Resolve an exact venue-city/country/state match, never the first search hit."""
    address = venue.get("address", {})
    country = {"USA": "US", "US": "US", "United States": "US", "Germany": "DE", "DE": "DE",
               "United Kingdom": "GB", "England": "GB", "Spain": "ES",
               "Mexico": "MX", "Brazil": "BR", "Ireland": "IE", "Australia": "AU", "France": "FR"}.get(address.get("country"))
    normalized = lambda text: "".join(c for c in unicodedata.normalize("NFKD", text).casefold() if not unicodedata.combining(c))
    city = normalized(address.get("city", ""))
    state = address.get("state")
    region = STATES.get(state, state) if country == "US" else None
    if not country or not city or (country == "US" and not region):
        raise ValueError("Venue city/country/state are incomplete")
    matches = [loc for loc in geocoding.get("results", [])
               if loc.get("country_code") == country and normalized(loc.get("name", "")) == city
               and (not region or loc.get("admin1") == region)]
    if len(matches) > 1 and address.get("zipCode"):
        postal = [loc for loc in matches if address["zipCode"] in (loc.get("postcodes") or [])]
        if postal:
            matches = postal
    if len(matches) > 1:
        administrative = [loc for loc in matches if loc.get("feature_code", "").startswith(("PPLA", "PPLC"))]
        municipalities = [loc for loc in matches if loc.get("feature_code") == "PPL"]
        if len(administrative) == 1:
            matches = administrative
        elif len(municipalities) == 1 and all(loc.get("feature_code") in {"PPL", "PPLX"} for loc in matches):
            matches = municipalities
    if len(matches) != 1:
        raise ValueError("Venue city coordinates are missing or ambiguous")
    return matches[0]


def depth_quarterbacks(payload, team_id):
    if str(payload.get("team", {}).get("id")) != str(team_id):
        raise ValueError("Depth chart team mismatch")
    entries = [player for group in payload.get("depthchart", [])
               for pos, value in group.get("positions", {}).items() if pos.lower() == "qb"
               for player in value.get("athletes", [])]
    if not entries:
        raise ValueError("Depth chart has no QB candidates")
    return [{"id": p["id"], "name": p["displayName"], "injuries": [
        {key: injury[key] for key in ("date", "status", "type") if key in injury}
        for injury in p.get("injuries", [])]} for p in entries]


def fetch_json(url, path):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    for attempt in range(2):
        try:
            with urlopen(Request(url, headers={"User-Agent": "NoFunLeaguePredictor/4.0"}), timeout=40) as response:
                content = response.read()
            break
        except (URLError, TimeoutError, OSError):
            if attempt:
                raise
    value = json.loads(content)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return value, {"url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                   "sha256": hashlib.sha256(content).hexdigest(), "status": "ok"}


def games_from_scoreboard(payload):
    games = []
    for event in payload.get("events", []):
        competition = event["competitions"][0]
        competitors = {c["homeAway"]: c for c in competition["competitors"]}
        status = competition.get("status", event.get("status", {})).get("type", {})
        home, away = competitors["home"], competitors["away"]
        if status.get("completed"):
            for competitor in (home, away):
                if competitor.get("score") is None or isinstance(competitor.get("score"), bool) or int(competitor["score"]) < 0:
                    raise ValueError("Completed game is missing a valid final score")
        state = status.get("state", "unknown")
        if state == "post" and not status.get("completed"):
            state = "unknown"
        games.append({"event_id": str(event["id"]), "kickoff": event["date"],
                      "week": int(event.get("week", payload.get("week", {})).get("number", 0)),
                      "home": home["team"]["abbreviation"], "away": away["team"]["abbreviation"],
                      "home_id": str(home["team"]["id"]), "away_id": str(away["team"]["id"]),
                      "home_score": int(home.get("score", 0)) if status.get("completed") else None,
                      "away_score": int(away.get("score", 0)) if status.get("completed") else None,
                      "completed": bool(status.get("completed")), "state": state,
                      "home_live_score": int(home["score"]) if home.get("score") is not None else None,
                      "away_live_score": int(away["score"]) if away.get("score") is not None else None,
                      "clock": competition.get("status", event.get("status", {})).get("displayClock"),
                      "period": competition.get("status", event.get("status", {})).get("period"),
                      "status_detail": status.get("shortDetail") or status.get("detail"),
                      "venue": competition.get("venue", {}), "sources": {}})
    ids = [g["event_id"] for g in games]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate scoreboard events")
    return games


def refresh(season, week, output):
    """Refresh all event scores and pending Sunday/Monday injury/depth evidence.

    This intentionally leaves stats, staff and official inactives unverified.
    Fresh downloads alone cannot turn the November 10 feature matrix current.
    """
    if output.exists():
        raise FileExistsError("Choose a new run directory")
    output.mkdir(parents=True)
    url = ESPN + "/scoreboard?" + urlencode({"dates": season, "seasontype": 2, "week": week, "limit": 1000})
    payload, receipt = fetch_json(url, output / "scoreboard.json")
    actual_year = payload.get("season", {}).get("year")
    actual_week = payload.get("week", {}).get("number")
    if actual_year != season or actual_week != week:
        raise ValueError(f"Scoreboard scope mismatch: {actual_year} week {actual_week}")
    games = games_from_scoreboard(payload)
    now = datetime.now(timezone.utc)
    from zoneinfo import ZoneInfo
    # NFL slate days are assigned in US Eastern time, including UTC Monday SNF.
    eastern = ZoneInfo("America/New_York")
    for game in games:
        game["week"] = week
        game["season"] = season
        game["slate_eligible"] = timestamp(game["kickoff"]).astimezone(eastern).weekday() in (6, 0)
        if not game["slate_eligible"] or game["state"] != "pre" or timestamp(game["kickoff"]) <= now:
            continue
        event_id = game["event_id"]
        venue_url = receipt["url"]
        try:
            summary, source = fetch_json(ESPN + "/summary?event=" + event_id,
                                         output / f"summary-{event_id}.json")
            if not isinstance(summary.get("injuries"), list):
                raise ValueError("Summary injury coverage is unavailable")
            game["sources"]["injuries"] = {**source, "event_id": event_id,
                                           "coverage": "ESPN reports; not official inactive confirmation"}
            game["venue"] = summary.get("gameInfo", {}).get("venue", game["venue"])
            venue_url = source["url"]
        except Exception as error:
            game["sources"]["injuries"] = {"status": "error", "error": str(error)}
        depth_sources = []
        for side in ("home", "away"):
            try:
                depth, source = fetch_json(ESPN + "/teams/" + game[side + "_id"] + "/depthcharts",
                                       output / f"depth-{event_id}-{side}.json")
                source["qb_candidates"] = depth_quarterbacks(depth, game[side + "_id"])
                depth_sources.append(source)
            except Exception as error:
                depth_sources.append({"status": "error", "error": str(error)})
        if all(s["status"] == "ok" for s in depth_sources):
            game["sources"]["depth"] = {**depth_sources[0], "event_id": event_id, "both_teams": depth_sources}
        else:
            game["sources"]["depth"] = {"status": "error", "both_teams": depth_sources}
        # Prefer venue coordinates; otherwise disclose a uniquely resolved city proxy.
        venue = game["venue"]
        latitude, longitude = venue.get("latitude"), venue.get("longitude")
        coordinate_source = {"scope": "Venue coordinates supplied by ESPN", "url": venue_url}
        if latitude is None or longitude is None:
            try:
                geo_url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode({
                    "name": venue.get("address", {}).get("city", ""), "count": 100, "language": "en", "format": "json"})
                geo, coordinate_source = fetch_json(geo_url, output / f"geocoding-{event_id}.json")
                city = unique_venue_city(venue, geo)
                latitude, longitude = city["latitude"], city["longitude"]
                coordinate_source["scope"] = "City-level proxy: exact unique venue city/country/state match; not stadium coordinates"
            except Exception as error:
                coordinate_source = {"status": "missing", "error": str(error)}
        if latitude is not None and longitude is not None:
            try:
                params = {"latitude": latitude, "longitude": longitude, "hourly": "temperature_2m,wind_speed_10m,wind_gusts_10m,precipitation_probability",
                          "temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "timezone": "UTC", "forecast_days": 16}
                weather, source = fetch_json("https://api.open-meteo.com/v1/forecast?" + urlencode(params),
                                             output / f"weather-{event_id}.json")
                hourly = weather["hourly"]
                times = [timestamp(t + "+00:00") for t in hourly["time"]]
                index = min(range(len(times)), key=lambda i: abs((times[i] - timestamp(game["kickoff"])).total_seconds()))
                game["sources"]["weather"] = {**source, "event_id": event_id, "valid_at": times[index].isoformat(),
                    "temperature_f": hourly["temperature_2m"][index], "wind_mph": hourly["wind_speed_10m"][index],
                    "gust_mph": hourly["wind_gusts_10m"][index],
                    "precip_probability": hourly["precipitation_probability"][index] / 100 if hourly["precipitation_probability"][index] is not None else None,
                    "units": {"temperature_f": "F", "wind_mph": "mph", "gust_mph": "mph", "precip_probability": "fraction 0-1"},
                    "coordinates": {"latitude": latitude, "longitude": longitude, "source": coordinate_source}}
            except Exception as error:
                game["sources"]["weather"] = {"status": "error", "error": str(error)}
        game["sources"].setdefault("weather", {"status": "missing", "reason": "Unambiguous venue/city coordinates or enclosed-roof evidence required", "coordinate_source": coordinate_source})
    result = {"season": season, "week": week, "retrieved_at": receipt["retrieved_at"],
              "scoreboard_source": receipt, "games": games}
    (output / "manifest.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result
