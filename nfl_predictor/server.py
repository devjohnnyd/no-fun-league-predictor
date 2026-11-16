"""Small same-origin scoreboard server for the portable dashboard."""
from datetime import datetime, timezone
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.request import Request, urlopen

from .dashboard import week_payload
from .sources import ESPN, games_from_scoreboard
from .storage import read_json


def fetch_week(season, week):
    url = f"{ESPN}/scoreboard?dates={season}&seasontype=2&week={week}&limit=1000"
    with urlopen(Request(url, headers={"User-Agent": "NoFunLeaguePredictor/4.0"}), timeout=20) as response:
        content = response.read()
    payload = json.loads(content)
    if payload.get("season", {}).get("year") != season or payload.get("week", {}).get("number") != week:
        raise ValueError("Provider returned a different season/week")
    fetched = datetime.now(timezone.utc).isoformat()
    games = games_from_scoreboard(payload)
    from zoneinfo import ZoneInfo
    from .freshness import timestamp
    for game in games:
        game["season"], game["week"] = season, week
        game["slate_eligible"] = timestamp(game["kickoff"]).astimezone(ZoneInfo("America/New_York")).weekday() in (6, 0)
    return {"season": season, "week": week, "retrieved_at": fetched, "games": games,
            "scoreboard_source": {"url": url, "retrieved_at": fetched, "status": "ok", "sha256": hashlib.sha256(content).hexdigest()}}


class WeekFeed:
    def __init__(self, season, week, metadata, batches, dataset=None, ttl=30, card=None):
        if not 2022 <= season <= datetime.now(timezone.utc).year + 1 or not 1 <= week <= 18:
            raise ValueError("Invalid NFL season/week")
        self.season, self.week = season, week
        self.metadata, self.batches, self.dataset = metadata, batches, dataset
        self.card = card
        self.ttl, self.cached, self.updated = ttl, None, 0.
        self.lock = threading.Lock()

    def get(self):
        with self.lock:
            if self.cached is None or time.monotonic() - self.updated >= self.ttl:
                manifest = fetch_week(self.season, self.week)
                result = week_payload(manifest, self.metadata, self.batches, self.dataset, self.card)
                self.cached, self.updated = result, time.monotonic()
            return self.cached


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, feed, logo_dir, **kwargs):
        self.feed, self.logo_dir = feed, Path(logo_dir).resolve()
        super().__init__(*args, **kwargs)

    def do_GET(self):
        route = self.path.split("?", 1)[0]
        if route.endswith("/live-week.json") or route == "/live-week.json":
            try:
                value, status = self.feed.get(), 200
            except Exception:
                value, status = {"error": "Score provider unavailable; retry later"}, 503
            data = json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if route == "/api/health":
            data = json.dumps({"status": "ok", "season": self.feed.season, "week": self.feed.week}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def translate_path(self, path):
        from urllib.parse import unquote
        route = unquote(path.split("?", 1)[0])
        if route.startswith("/team-logos/"):
            target = (self.logo_dir / route.removeprefix("/team-logos/")).resolve()
            if target.is_relative_to(self.logo_dir) and target.is_file():
                return str(target)
            return str(self.logo_dir / "not-found")
        return super().translate_path(path)

    def list_directory(self, path):
        self.send_error(404, "Not found")
        return None


def serve(web, metadata_path, batch_paths, dataset_path, season, week, host="127.0.0.1", port=4173, logos=None, card_path=None):
    web = Path(web).resolve()
    if not (web / "index.html").is_file():
        raise ValueError("Build the dashboard before serving it")
    feed = WeekFeed(season, week, read_json(metadata_path), [read_json(p) for p in batch_paths], read_json(dataset_path) if dataset_path else None, card=read_json(card_path) if card_path else None)
    handler = partial(DashboardHandler, directory=str(web), feed=feed, logo_dir=logos or web / "team-logos")
    server = ThreadingHTTPServer((host, port), handler)
    print(f"NFL dashboard: http://{host}:{port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
