"""Durable weekly preparation and pregame checks for the single-worker host.

UTC job keys, an expiring coordinator lease and immutable refresh receipts let
restarts recover work. This is preparation, not continuous market collection.
"""
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import json
import logging
from pathlib import Path
import sqlite3
import threading
import uuid
from zoneinfo import ZoneInfo

from .freshness import timestamp

log = logging.getLogger(__name__)
UTC = timezone.utc


def planned_jobs(dataset, season, now):
    """Group the real schedule's kickoffs; never guess a Sunday-only slate."""
    groups, weeks = {}, {}
    for game in dataset.get("schedule", []):
        if game.get("season") != season or not game.get("espn") or game.get("home_score") is not None:
            continue
        try:
            kickoff = datetime.fromisoformat(f"{game['gameday']}T{game['gametime']}").replace(tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)
        except (KeyError, TypeError, ValueError):
            continue
        if not now + timedelta(minutes=5) < kickoff <= now + timedelta(days=7):
            continue
        week, event = game["week"], str(game["espn"])
        groups.setdefault((week, kickoff), []).append(event)
        weeks.setdefault(week, []).append(kickoff)
    jobs = []
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for week, kickoffs in weeks.items():
        jobs.append({"key": f"{season}:{week}:stats:{now.date()}", "week": week, "mode": "full", "final": False,
                     "events": None, "due": midnight.timestamp(),
                     "expires": min(midnight + timedelta(days=1), max(kickoffs) - timedelta(minutes=5)).timestamp()})
    for (week, kickoff), events in groups.items():
        for minutes, end_minutes, final in ((360, 90, False), (90, 30, True), (30, 5, True)):
            jobs.append({"key": f"{season}:{week}:{kickoff.isoformat()}:{minutes}", "week": week, "mode": "context", "final": final,
                         "events": sorted(events), "due": (kickoff - timedelta(minutes=minutes)).timestamp(),
                         "expires": (kickoff - timedelta(minutes=end_minutes)).timestamp()})
    return jobs


class WeeklyAutomation:
    def __init__(self, manager, path, clock=None):
        self.manager, self.path = manager, Path(path)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.owner = uuid.uuid4().hex
        self.stop_event, self.thread = threading.Event(), None
        self.lock = threading.Lock()
        self.error = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS coordinator (id INTEGER PRIMARY KEY, owner TEXT, expires REAL);
                CREATE TABLE IF NOT EXISTS jobs (
                    key TEXT PRIMARY KEY, spec TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'waiting',
                    attempts INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL,
                    run_id TEXT, started_at REAL, completed_at REAL, message TEXT);
            """)

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
            self.thread = threading.Thread(target=self.loop, daemon=True, name="nfl-weekly-preparation")
            self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        # Let the lease expire if analysis is still finishing. A second worker
        # must not begin overlapping work while this process is shutting down.

    def loop(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
                self.error = None
            except Exception:
                log.exception("Weekly preparation check failed")
                self.error = "Automatic preparation check failed; retrying in one minute."
            self.stop_event.wait(60)

    def tick(self):
        with self.lock:
            now = self.clock()
            seconds = now.timestamp()
            plans = planned_jobs(self.manager.dataset or {}, self.manager.season, now)
            specs = {p["key"]: p for p in plans}
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                lease = db.execute("SELECT * FROM coordinator WHERE id=1").fetchone()
                if lease and lease["owner"] != self.owner and lease["expires"] > seconds:
                    return
                db.execute("INSERT OR REPLACE INTO coordinator VALUES (1, ?, ?)", (self.owner, seconds + 300))
                for spec in plans:
                    db.execute("INSERT OR IGNORE INTO jobs(key,spec,next_at) VALUES(?,?,?)", (spec["key"], json.dumps(spec), spec["due"]))
                active = db.execute("SELECT * FROM jobs WHERE state='running' ORDER BY started_at LIMIT 1").fetchone()
                status = dict(self.manager.refresh.status)
                if active:
                    if active["run_id"] != status.get("runId") and hasattr(self.manager.refresh, "receipt"):
                        status = self.manager.refresh.receipt(active["run_id"]) or status
                    if active["run_id"] == status.get("runId") and status["state"] == "running":
                        return
                    finished = active["run_id"] == status.get("runId") and status["state"] == "complete" and not status.get("blockedGames")
                    spec = json.loads(active["spec"])
                    message = status.get("message", "") if active["run_id"] == status.get("runId") else "Interrupted preparation; retrying after restart."
                    db.execute("UPDATE jobs SET state=?,next_at=?,completed_at=?,message=? WHERE key=?",
                               ("complete" if finished else "waiting", seconds + (3600 if spec["mode"] == "full" else 600), seconds, message, active["key"]))
                # Manual jobs share the analysis lock and must finish first.
                if self.manager.refresh.status["state"] == "running":
                    return
                candidates = [dict(row) for row in db.execute("SELECT * FROM jobs WHERE state='waiting' AND next_at<=?", (seconds,))
                              if row["key"] in specs and specs[row["key"]]["due"] <= seconds < specs[row["key"]]["expires"]]
                # Reuse a fresh fitted model before doing another heavy build.
                candidates.sort(key=lambda row: (0 if specs[row["key"]]["mode"] == "context" and self.manager.refresh.cached_models(specs[row["key"]]["week"], now) else 1,
                                                  specs[row["key"]]["due"]))
                for row in candidates:
                    spec = specs[row["key"]]
                    if spec["mode"] == "full":
                        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
                        full_today = db.execute("SELECT spec,attempts FROM jobs WHERE key LIKE ?", (f"{self.manager.season}:%:stats:{now.date()}",)).fetchall()
                        if sum(r["attempts"] for r in full_today) >= 6:
                            db.execute("UPDATE jobs SET next_at=?,message=? WHERE key=?", (day_start + 86400, "Daily preparation attempt limit reached; continuing with the next UTC day.", row["key"]))
                            continue
                        # A successful manual release can satisfy today's job.
                        cached = self.manager.refresh.cached_models(spec["week"], now)
                        if cached and timestamp_from_ready(cached) >= day_start and status.get("week") == spec["week"] and status["state"] == "complete" and not status.get("blockedGames"):
                            db.execute("UPDATE jobs SET state='complete',completed_at=?,message=? WHERE key=?",
                                       (seconds, "Recent full preparation already completed; pregame checks remain scheduled.", row["key"]))
                            continue
                    elif self.manager.refresh.cached_models(spec["week"], now) is None:
                        db.execute("UPDATE jobs SET next_at=?,message=? WHERE key=?", (seconds + 600, "Waiting for complete statistics and recent fitted models.", row["key"]))
                        continue
                    # Retry missing context without redownloading/retraining
                    # statistics already prepared successfully today.
                    mode = "context" if spec["mode"] == "full" and cached and timestamp_from_ready(cached) >= day_start else spec["mode"]
                    result = self.manager.refresh.start(spec["week"], mode=mode, event_ids=spec["events"], final=spec["final"])
                    db.execute("UPDATE jobs SET state=?,attempts=attempts+1,started_at=?,run_id=?,message=?,next_at=? WHERE key=?",
                               ("running" if result["state"] == "running" else "waiting", seconds, result["runId"], result["message"], seconds + 3600, row["key"]))
                    break

    def status(self):
        now = self.clock().timestamp()
        plans = {p["key"]: p for p in planned_jobs(self.manager.dataset or {}, self.manager.season, self.clock())}
        with self.connect() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY COALESCE(completed_at,started_at,0) DESC")]
        pending = [row for row in rows if row["state"] == "waiting" and row["key"] in plans and plans[row["key"]]["expires"] > now]
        pending.sort(key=lambda row: max(row["next_at"], plans[row["key"]]["due"]))
        next_job = pending[0] if pending else None
        return {"enabled": self.thread is not None and self.thread.is_alive(), "error": self.error,
                "cadence": "Daily statistics preparation; pregame checks at 6 hours, 90 minutes and 30 minutes before kickoff.",
                "nextCheckAt": datetime.fromtimestamp(max(now, next_job["next_at"]), UTC).isoformat() if next_job else None,
                "nextWeek": plans[next_job["key"]]["week"] if next_job else None,
                "recent": [{"week": json.loads(row["spec"])["week"], "mode": json.loads(row["spec"])["mode"],
                            "final": json.loads(row["spec"])["final"], "state": row["state"], "attempts": row["attempts"],
                            "message": row["message"], "completedAt": datetime.fromtimestamp(row["completed_at"], UTC).isoformat() if row["completed_at"] else None}
                           for row in rows if row["attempts"]][:8]}


def timestamp_from_ready(root):
    from .storage import read_json
    return timestamp(read_json(root / "models-ready.json")["createdAt"]).timestamp()
