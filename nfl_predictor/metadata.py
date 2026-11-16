"""Team branding and city-level venue metadata from NFL/ESPN/Open-Meteo."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .features import normalize_team
from .sources import ESPN, fetch_json, unique_venue_city
from .storage import read_json, write_new


class LogoParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = {}

    def handle_starttag(self, tag, attrs):
        if tag != "img":
            return
        attrs = dict(attrs)
        name = attrs.get("alt", "").removesuffix(" logo").removesuffix(" Logo")
        url = attrs.get("data-src") or attrs.get("src", "")
        if name and "static.www.nfl.com/" in url:
            self.images[name] = url


def acquire_metadata(dataset_path, output, assets):
    output, assets = Path(output), Path(assets)
    if output.exists():
        raise FileExistsError(output)
    assets.mkdir(parents=True, exist_ok=True)
    raw = output.parent / (output.stem + "-raw")
    raw.mkdir(parents=True, exist_ok=False)
    dataset = read_json(dataset_path)
    listing, listing_source = fetch_json(ESPN + "/teams?limit=100", raw / "teams.json")
    teams = [item["team"] for item in listing["sports"][0]["leagues"][0]["teams"]]
    nfl_url = "https://www.nfl.com/teams/"
    with urlopen(Request(nfl_url, headers={"User-Agent": "NoFunLeaguePredictor/4.0"}), timeout=30) as response:
        html = response.read()
    (raw / "nfl-teams.html").write_bytes(html)
    logos = LogoParser()
    logos.feed(html.decode("utf-8"))
    result = {"created_at": datetime.now(timezone.utc).isoformat(), "teams": {}, "stadiums": {}, "games": {}, "team_homes": {},
              "sources": [listing_source, {"url": nfl_url, "sha256": hashlib.sha256(html).hexdigest(),
                           "retrieved_at": datetime.now(timezone.utc).isoformat()}], "errors": [],
              "travel_scope": "Straight-line distance between home-city and venue-city proxies; not actual travel itineraries. Historical venue mappings are restricted to the same NFL stadium ID as current home venues."}

    def collect(team):
        code = normalize_team(team["abbreviation"])
        entry = {"code": code, "id": str(team["id"]), "name": team["displayName"],
                 "color": team.get("color"), "alternate_color": team.get("alternateColor")}
        receipts, error = [], None
        try:
            detail, receipt = fetch_json(ESPN + "/teams/" + entry["id"], raw / f"team-{code}.json")
            receipts.append(receipt)
            venue = detail["team"]["franchise"]["venue"]
            geo_url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode({"name": venue["address"]["city"], "count": 100, "language": "en", "format": "json"})
            geo, receipt = fetch_json(geo_url, raw / f"city-{code}.json")
            receipts.append(receipt)
            city = unique_venue_city(venue, geo)
            entry["home_venue"] = {"name": venue["fullName"], "latitude": city["latitude"], "longitude": city["longitude"],
                                    "timezone": city["timezone"], "city": venue["address"]["city"],
                                    "coordinate_scope": "City-level proxy", "source": receipt}
            entry["logo_url"] = logos.images.get(entry["name"])
            if not entry["logo_url"]:
                raise ValueError("Official NFL logo not found")
            with urlopen(Request(entry["logo_url"], headers={"User-Agent": "NoFunLeaguePredictor/4.0"}), timeout=30) as response:
                image = response.read()
                mime = response.headers.get_content_type()
            ext = {"image/svg+xml": "svg", "image/png": "png", "image/webp": "webp", "image/jpeg": "jpg"}.get(mime)
            if not ext:
                raise ValueError("Unexpected logo content type: " + mime)
            target = assets / f"{code.lower()}.{ext}"
            if target.exists():
                if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(image).digest():
                    raise ValueError("Existing logo differs; use a new asset directory")
            else:
                with target.open("xb") as stream:
                    stream.write(image)
            entry["logo_file"] = target.name
            entry["logo_sha256"] = hashlib.sha256(image).hexdigest()
        except Exception as exc:
            error = {"team": code, "error": str(exc)}
        return entry, receipts, error

    with ThreadPoolExecutor(max_workers=4) as pool:
        collected = list(pool.map(collect, teams))
    latest_season = max(g["season"] for g in dataset["schedule"])
    for entry, receipts, error in collected:
        code = entry["code"]
        result["teams"][code] = entry
        result["sources"].extend(receipts)
        if error:
            result["errors"].append(error)
        if "home_venue" in entry:
            home = entry["home_venue"]
            result["team_homes"][code] = home
            current = [g for g in dataset["schedule"] if g["season"] == latest_season and g["home_team"] == code and g.get("location") != "Neutral"]
            for game in current:
                if game.get("stadium_id"):
                    result["stadiums"][game["stadium_id"]] = home
    neutral = {}
    for game in dataset["schedule"]:
        if game.get("location") == "Neutral" and game.get("stadium_id") and game.get("espn"):
            neutral[(game["stadium_id"], game.get("stadium"))] = game
    for (stadium, stadium_name), game in neutral.items():
        file_id = game["game_id"]
        try:
            summary, source = fetch_json(ESPN + "/summary?event=" + game["espn"], raw / f"neutral-{file_id}.json")
            result["sources"].append(source)
            venue = summary["gameInfo"]["venue"]
            url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode({"name": venue["address"]["city"], "count": 100, "language": "en", "format": "json"})
            geo, source = fetch_json(url, raw / f"neutral-city-{file_id}.json")
            result["sources"].append(source)
            city = unique_venue_city(venue, geo)
            neutral_venue = {"latitude": city["latitude"], "longitude": city["longitude"], "timezone": city["timezone"],
                                             "city": venue["address"]["city"], "name": venue["fullName"], "source": source,
                                             "coordinate_scope": "City-level proxy"}
            for matching in dataset["schedule"]:
                if matching.get("location") == "Neutral" and (matching.get("stadium_id"), matching.get("stadium")) == (stadium, stadium_name):
                    result["games"][matching["game_id"]] = neutral_venue
        except Exception as exc:
            result["errors"].append({"stadium": stadium, "error": str(exc)})
    write_new(output, result)
    return result
