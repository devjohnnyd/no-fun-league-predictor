"""Background scoreboard/total collection, independent of model preparation."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import sqlite3
import threading
import uuid
from zoneinfo import ZoneInfo

from .freshness import timestamp

UTC = timezone.utc
log = logging.getLogger(__name__)


def active_weeks(dataset, season, now):
    """Include nearby kickoffs and games awaiting final scores; all NFL days."""
    weeks = set()
    for game in dataset.get("schedule", []):
        if game.get("season") != season or not game.get("espn") or game.get("home_score") is not None:
            continue
        try:
            kickoff = datetime.fromisoformat(f"{game['gameday']}T{game['gametime']}").replace(tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)
        except (KeyError, TypeError, ValueError):
            continue
        if now - timedelta(hours=12) <= kickoff <= now + timedelta(days=8):
            weeks.add(game["week"])
    return sorted(weeks)


def collection_interval(rows, now):
    if any(row["state"] == "in" for row in rows):
        return 60
    upcoming = [timestamp(row["kickoff"]) for row in rows if row["state"] == "pre" and timestamp(row["kickoff"]) > now]
    if upcoming:
        hours = (min(upcoming) - now).total_seconds() / 3600
        return 60 if hours <= 2 else 300 if hours <= 24 else 900
    return 900


class MarketCollection:
    def __init__(self, manager, path, clock=None):
        self.manager, self.path = manager, Path(path)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.owner = uuid.uuid4().hex
        self.thread, self.stop_event = None, threading.Event()
        self.lock = threading.Lock()
        self.error = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS polls (
                season INTEGER, week INTEGER, next_at REAL NOT NULL,
                lease_owner TEXT, lease_until REAL, last_attempt REAL, last_success REAL,
                last_quote REAL, failures INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'waiting',
                message TEXT, quoted_games INTEGER NOT NULL DEFAULT 0, missing_games INTEGER NOT NULL DEFAULT 0,
                complete INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(season,week))""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self.loop, daemon=True, name="nfl-background-markets")
            self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)

    def loop(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
                self.error = None
            except Exception:
                log.exception("Background market collection failed")
                self.error = "Background line collection interrupted; retrying shortly."
            self.stop_event.wait(30)

    def tick(self):
        with self.lock:
            for week in active_weeks(self.manager.dataset or {}, self.manager.season, self.clock()):
                if self.stop_event.is_set():
                    return
                now = self.clock().timestamp()
                with self.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("INSERT OR IGNORE INTO polls(season,week,next_at) VALUES(?,?,?)", (self.manager.season, week, now))
                    row = db.execute("SELECT * FROM polls WHERE season=? AND week=?", (self.manager.season, week)).fetchone()
                    if row["complete"] or row["next_at"] > now or (row["lease_until"] or 0) > now:
                        continue
                    db.execute("UPDATE polls SET lease_owner=?,lease_until=?,last_attempt=?,state='collecting' WHERE season=? AND week=?",
                               (self.owner, now + 120, now, self.manager.season, week))
                # Never hold a database transaction during a provider request.
                try:
                    payload = self.manager.feed(week).get()
                    rows = payload["queries"]["matchups"]["rows"]
                    observed = timestamp(payload["queries"]["matchups"]["source"]["executedAt"])
                    checked = self.clock()
                    if (payload["period"]["season"], payload["period"]["week"]) != (self.manager.season, week) or not rows:
                        raise ValueError("Missing or conflicting weekly source scope")
                    if not 0 <= (checked - observed).total_seconds() <= 120:
                        raise ValueError("Source snapshot is stale or future-dated")
                    eligible = [r for r in rows if r["state"] == "pre" and timestamp(r["kickoff"]) > checked]
                    quoted = [r for r in eligible if r.get("marketTotal", {}).get("quoteStatus") == "pregame"
                              and timestamp(r["marketTotal"]["observedAt"]) == observed]
                    missing = len(eligible) - len(quoted)
                    finished = all(r["state"] == "post" and timestamp(r["kickoff"]) <= checked for r in rows)
                    state = "complete" if finished else "partial" if missing else "ok"
                    message = f"{len(quoted)} pregame {'game' if len(quoted) == 1 else 'games'} with quotes; {missing} without a current quote." if not finished else "All games final; collection finished for this week."
                    next_at = checked.timestamp() + collection_interval(rows, checked)
                    with self.connect() as db:
                        db.execute("""UPDATE polls SET next_at=?,lease_until=0,last_success=?,last_quote=COALESCE(?,last_quote),
                            failures=0,state=?,message=?,quoted_games=?,missing_games=?,complete=?
                            WHERE season=? AND week=? AND lease_owner=?""",
                            (next_at, observed.timestamp(), observed.timestamp() if quoted else None, state, message, len(quoted), missing,
                             int(finished), self.manager.season, week, self.owner))
                except Exception:
                    log.exception("Week %s market collection failed", week)
                    with self.connect() as db:
                        # Retain source/quote times and all existing observations.
                        failures = row["failures"] + 1
                        db.execute("""UPDATE polls SET next_at=?,lease_until=0,failures=?,state='failed',message=?
                            WHERE season=? AND week=? AND lease_owner=?""",
                            (self.clock().timestamp() + min(900, 60 * 2 ** min(failures - 1, 4)), failures,
                             "Provider check failed; keeping previous quotes and retrying.", self.manager.season, week, self.owner))

    def status(self):
        weeks = active_weeks(self.manager.dataset or {}, self.manager.season, self.clock())
        with self.connect() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM polls WHERE season=? ORDER BY week", (self.manager.season,))]
        def iso(value):
            return datetime.fromtimestamp(value, UTC).isoformat() if value is not None else None
        return {"enabled": self.thread is not None and self.thread.is_alive(), "error": self.error, "provider": "ESPN-listed sportsbook quotes",
                "cadence": "Every 15 minutes; every 5 minutes within 24 hours of kickoff; every minute within 2 hours and during live games.",
                "weeks": [{"week":row["week"], "state":row["state"], "message":row["message"], "failures":row["failures"],
                           "lastAttemptAt":iso(row["last_attempt"]), "lastSuccessAt":iso(row["last_success"]), "lastQuoteAt":iso(row["last_quote"]),
                           "nextCheckAt":iso(max(row["next_at"], row["lease_until"] or 0)) if not row["complete"] and row["week"] in weeks else None,
                           "quotedGames":row["quoted_games"], "missingQuotes":row["missing_games"]} for row in rows]}
