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
from .features import normalize_team
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
    def __init__(self, season, week, metadata, batches, dataset=None, ttl=30, card=None, line_tracker=None):
        if not 2022 <= season <= datetime.now(timezone.utc).year + 1 or not 1 <= week <= 18:
            raise ValueError("Invalid NFL season/week")
        self.season, self.week = season, week
        self.metadata, self.batches, self.dataset = metadata, batches, dataset
        self.card = card
        self.line_tracker = line_tracker
        self.strict_slate = dataset is not None
        if dataset is not None:
            self.expected_games = {str(g["espn"]): (g["home_team"], g["away_team"])
                                   for g in dataset["schedule"] if g["season"] == season and g["week"] == week and g.get("espn")}
        else:
            prefix = f"{season}_{week:02d}_"
            self.expected_games = {str(g["espn_id"]): (g["home"], g["away"])
                                   for batch in batches for g in batch["forecast"]
                                   if g.get("game_id", "").startswith(prefix) or
                                   (batch.get("season"), batch.get("week")) == (season, week)}
        if not self.expected_games:
            raise ValueError("No schedule or saved forecast identities for this season/week")
        self.ttl, self.cached, self.updated = ttl, None, 0.
        self.lock = threading.Lock()

    def get(self):
        with self.lock:
            if self.cached is None or time.monotonic() - self.updated >= self.ttl:
                manifest = fetch_week(self.season, self.week)
                actual = {str(g["event_id"]): (normalize_team(g["home"]), normalize_team(g["away"])) for g in manifest["games"]}
                missing = self.expected_games.keys() - actual.keys()
                extra = actual.keys() - self.expected_games.keys()
                if missing or (self.strict_slate and extra) or len(actual) != len(manifest["games"]):
                    raise ValueError("Incomplete or conflicting weekly score feed; retaining the last complete slate")
                if any(actual[event] != teams for event, teams in self.expected_games.items()):
                    raise ValueError("Weekly score feed team identity changed")
                result = week_payload(manifest, self.metadata, self.batches, self.dataset, self.card)
                if self.line_tracker:
                    result = self.line_tracker.enrich(result, manifest, self.batches)
                # Forecast-only feeds may initially omit an unforecasted game.
                # Allow growth when it returns, while protecting all seen games.
                # The browser independently checks its full reviewed slate.
                self.expected_games = actual
                self.cached, self.updated = result, time.monotonic()
            return self.cached


class SeasonFeeds:
    def __init__(self, season, week, metadata_path, batch_paths, dataset_path, card_path, state_dir, history_bundles, staff_seed):
        from .line_tracking import LineTracker
        from .refresh_job import AnalysisRefresh
        self.season, self.week = season, week
        self.metadata_path, self.staff_seed = metadata_path, staff_seed
        self.metadata, self.dataset = read_json(metadata_path), read_json(dataset_path) if dataset_path else None
        self.batches = [read_json(path) for path in batch_paths]
        self.card_path = card_path
        self.state_dir = Path(state_dir)
        self.line_tracker = LineTracker(self.state_dir / "lines.sqlite3")
        # Reload immutable revisions from earlier local refresh sessions.
        for path in sorted((self.state_dir / "refreshes").glob("*/release/forecast.json")):
            self.batches.append(read_json(path))
            refreshed_dataset = path.parents[1] / "dataset.json.gz"
            reference = path.parents[1] / "dataset-reference.json"
            if reference.is_file():
                pointer = read_json(reference)
                refreshed_dataset = (self.state_dir / "refreshes" / pointer["path"]).resolve()
                if not refreshed_dataset.is_relative_to((self.state_dir / "refreshes").resolve()) or hashlib.sha256(refreshed_dataset.read_bytes()).hexdigest() != pointer["sha256"]:
                    raise ValueError("Saved forecast dataset reference failed integrity verification")
            if refreshed_dataset.is_file():
                self.dataset = read_json(refreshed_dataset)
        self.feeds, self.lock = {}, threading.RLock()
        self.refresh = AnalysisRefresh(self, history_bundles, self.state_dir / "refreshes")
        from .automation import WeeklyAutomation
        self.automation = WeeklyAutomation(self, self.state_dir / "preparation.sqlite3")
        from .market_collection import MarketCollection
        self.market_collection = MarketCollection(self, self.state_dir / "market-collection.sqlite3")

    def feed(self, week):
        if not 1 <= week <= 18:
            raise ValueError("Invalid NFL week")
        with self.lock:
            if week not in self.feeds:
                card_directory = self.card_path.parent if self.card_path else Path("data/cards")
                card_path = self.card_path if week == self.week and self.card_path else card_directory / f"{self.season}-week{week}.json"
                card = read_json(card_path) if card_path.is_file() else None
                result = WeekFeed(self.season, week, self.metadata, self.batches, self.dataset, card=card, line_tracker=self.line_tracker)
                result.card_path = card_path if card else None
                self.feeds[week] = result
            return self.feeds[week]

    def install(self, dataset, batch, path):
        with self.lock:
            self.dataset = dataset
            self.batches = [*self.batches, batch]
            self.feeds = {}


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, feed, logo_dir, **kwargs):
        self.feed, self.logo_dir = feed, Path(logo_dir).resolve()
        super().__init__(*args, **kwargs)

    def do_GET(self):
        from urllib.parse import parse_qs, urlsplit
        params = parse_qs(urlsplit(self.path).query)
        try:
            week = int(params.get("week", [self.feed.week])[0])
            if not 1 <= week <= 18:
                raise ValueError()
        except ValueError:
            self.send_error(400, "Invalid week")
            return
        route = self.path.split("?", 1)[0]
        if route == "/api/refresh":
            self.send_json({**self.feed.refresh.status, "automation": self.feed.automation.status(), "marketCollection": self.feed.market_collection.status()})
            return
        if route.endswith("/live-week.json") or route == "/live-week.json":
            try:
                active = self.feed.feed(week)
                if params.get("refresh") == ["1"]:
                    active.updated = 0
                value, status = active.get(), 200
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

    def send_json(self, value, status=200):
        data = json.dumps(value, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/api/refresh":
            self.send_error(404)
            return
        # Refresh can make many external reads; reject cross-site triggers.
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{self.headers.get('Host')}":
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 128:
                raise ValueError()
            body = json.loads(self.rfile.read(length))
            week = int(body["week"])
            self.feed.feed(week)
        except (ValueError, KeyError, TypeError, OverflowError, json.JSONDecodeError):
            self.send_error(400)
            return
        self.send_json(self.feed.refresh.start(week), 202)

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


def serve(web, metadata_path, batch_paths, dataset_path, season, week, host="127.0.0.1", port=4173, logos=None, card_path=None, state_dir="work/tracker", history_bundles=(), staff_seed="archive/session-2026-11-10/enhanced/context.json"):
    web = Path(web).resolve()
    if not (web / "index.html").is_file():
        raise ValueError("Build the dashboard before serving it")
    feed = SeasonFeeds(season, week, metadata_path, batch_paths, dataset_path, card_path, state_dir, history_bundles, staff_seed)
    handler = partial(DashboardHandler, directory=str(web), feed=feed, logo_dir=logos or web / "team-logos")
    server = ThreadingHTTPServer((host, port), handler)
    print(f"NFL dashboard: http://{host}:{port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
