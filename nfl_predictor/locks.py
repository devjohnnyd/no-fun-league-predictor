"""Locked bets: an immutable pregame snapshot per game, compared with what changed afterward."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import time

from .freshness import timestamp

PASSWORD_ENV = "NFL_LOCK_PASSWORD"
FAILED_PASSWORD_DELAY_SECONDS = 1
PROBABILITY_SHIFT = .03
WIND_SHIFT_MPH = 5
TEMPERATURE_SHIFT_F = 10
PRECIP_SHIFT = .25
SERIOUS_STATUSES = {"Out", "Doubtful", "Injured Reserve", "Suspension", "Physically Unable to Perform"}


class LockError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def check_password(given):
    """The password lives only in the server environment; without it, locking is off."""
    expected = os.environ.get(PASSWORD_ENV)
    if not expected:
        raise LockError("Locking is not configured on this server.", 503)
    if not isinstance(given, str) or not hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
        time.sleep(FAILED_PASSWORD_DELAY_SECONDS)
        raise LockError("Incorrect lock password.", 403)


def moment(value):
    """Batch dates without a time count as the end of that day, matching the dashboard."""
    return timestamp(value + "T23:59:59+00:00" if len(value) == 10 else value)


def projected_qbs(row, inputs):
    """A newer input check outranks the last released forecast, which a QB change can block."""
    current = {"source": "Saved forecast", "checkedAt": row.get("forecastIssuedAt"),
               "home": {"name": row.get("homeQb"), "status": row.get("homeQbStatus")},
               "away": {"name": row.get("awayQb"), "status": row.get("awayQbStatus")}}
    check = (inputs or {}).get(row["eventId"])
    if check and check.get("qbs") and (not row.get("forecastIssuedAt") or moment(check["checkedAt"]) > moment(row["forecastIssuedAt"])):
        current = {"source": "Latest input check", "checkedAt": check["checkedAt"], **check["qbs"]}
    return current


def market_view(market, probabilities, projection_key):
    if not market:
        return None
    analysis = market.get("analysis")
    return {"line": market.get("latestLine"), "book": market.get("book"), "observedAt": market.get("observedAt"),
            "quoteStatus": market.get("quoteStatus"), "lean": analysis.get("lean") if analysis else None,
            "probability": max(analysis[key] for key in probabilities) if analysis else None,
            "projection": (market.get("projection") or {}).get(projection_key)}


def snapshot(row, inputs):
    return {"pick": row["pick"], "homeProbability": row["homeProbability"], "pickProbability": row["pickProbability"],
            "stage": row.get("predictionStage"), "forecastIssuedAt": row.get("forecastIssuedAt"), "model": row.get("modelName"),
            "qbs": projected_qbs(row, inputs),
            "injuries": {"home": row.get("homeInjuries") or [], "away": row.get("awayInjuries") or []},
            "weather": row.get("weather"),
            "spread": market_view(row.get("marketSpread"), ("home_cover_probability", "away_cover_probability"), "projected_home_margin"),
            "total": market_view(row.get("marketTotal"), ("over_probability", "under_probability"), "projected_total"),
            "sources": {kind: source.get("retrieved_at") for kind, source in (row.get("forecastSources") or {}).items() if isinstance(source, dict)}}


def changes(locked, row, inputs):
    """Material differences between the locked snapshot and what is known now; 'major' could flip a bet."""
    found = []
    def note(kind, label, before, after, major=False):
        found.append({"kind": kind, "label": label, "before": before, "after": after, "severity": "major" if major else "minor"})
    current = projected_qbs(row, inputs)
    for side in ("home", "away"):
        code, then, now = row[side + "Code"], locked["qbs"][side], current[side]
        if not now.get("name") or not then.get("name"):
            continue
        if now["name"] != then["name"]:
            note("qb", f"{code} starting QB changed", then["name"], now["name"], True)
        elif now.get("status") != then.get("status"):
            note("qb", f"{code} QB status changed", then.get("status"), now.get("status"), now.get("status") in SERIOUS_STATUSES)
    if row.get("pick") and row["pick"] != locked["pick"]:
        note("pick", "Model now picks the other team", locked["pick"], row["pick"], True)
    if row.get("homeProbability") is not None and abs(row["homeProbability"] - locked["homeProbability"]) >= PROBABILITY_SHIFT:
        side = "home" if locked["pick"] == row["homeCode"] else "away"
        then_p = locked["homeProbability"] if side == "home" else 1 - locked["homeProbability"]
        now_p = row["homeProbability"] if side == "home" else 1 - row["homeProbability"]
        note("probability", f"{locked['pick']} win probability", f"{round(then_p * 100)}%", f"{round(now_p * 100)}%")
    for market, field, probabilities, projection in (("spread", "marketSpread", ("home_cover_probability", "away_cover_probability"), "projected_home_margin"),
                                                     ("total", "marketTotal", ("over_probability", "under_probability"), "projected_total")):
        then, now = locked.get(market), market_view(row.get(field), probabilities, projection)
        if not then or not now:
            continue
        if then["line"] is not None and now["line"] is not None and now["line"] != then["line"]:
            note(market, f"{market.title()} line moved", then["line"], now["line"])
        if then["lean"] and now["lean"] and now["lean"] != then["lean"]:
            note(market, f"{market.title()} lean flipped", then["lean"], now["lean"], True)
    for side in ("home", "away"):
        then = {r["name"]: r["status"] for r in locked["injuries"][side]}
        now = {r["name"]: r["status"] for r in row.get(side + "Injuries") or []}
        for name in sorted(now.keys() | then.keys()):
            if then.get(name) != now.get(name):
                note("injury", f"{row[side + 'Code']} {name}", then.get(name) or "Not listed", now.get(name) or "No longer listed",
                     now.get(name) in SERIOUS_STATUSES and then.get(name) not in SERIOUS_STATUSES)
    then_w, now_w = locked.get("weather") or {}, row.get("weather") or {}
    for key, label, limit, unit in (("wind_mph", "Wind", WIND_SHIFT_MPH, " mph"), ("temperature_f", "Temperature", TEMPERATURE_SHIFT_F, "°F"),
                                    ("precip_probability", "Rain chance", PRECIP_SHIFT, "")):
        if then_w.get(key) is not None and now_w.get(key) is not None and abs(now_w[key] - then_w[key]) >= limit:
            show = (lambda v: f"{round(v * 100)}%") if key == "precip_probability" else (lambda v: f"{round(v)}{unit}")
            note("weather", label, show(then_w[key]), show(now_w[key]))
    return found


def market_outcome(lean, line, actual, outcomes, spread):
    if lean not in outcomes or line is None:
        return None
    threshold = -line if spread else line
    result = outcomes[0] if actual > threshold else outcomes[1] if actual < threshold else "Push"
    return "Push" if result == "Push" else "Won" if result == lean else "Lost"


def result(locked, row):
    """Grade the bet exactly as locked; the latest pick is hindsight, never a rewrite."""
    if row.get("state") != "post" or row.get("homeScore") is None or row.get("awayScore") is None:
        return None
    margin, total = row["homeScore"] - row["awayScore"], row["homeScore"] + row["awayScore"]
    winner = None if margin == 0 else row["homeCode"] if margin > 0 else row["awayCode"]
    spread, over_under = locked.get("spread") or {}, locked.get("total") or {}
    graded = {"winner": "Tie" if winner is None else "Won" if winner == locked["pick"] else "Lost",
              "spread": market_outcome(spread.get("lean"), spread.get("line"), margin, ("Home", "Away"), True),
              "total": market_outcome(over_under.get("lean"), over_under.get("line"), total, ("Over", "Under"), False)}
    if winner and row.get("pick") and row["pick"] != locked["pick"]:
        graded["latestPick"] = {"pick": row["pick"], "outcome": "Won" if winner == row["pick"] else "Lost"}
    return graded


class PickLocks:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS locks (season INTEGER, week INTEGER, event TEXT, locked_at TEXT, snapshot TEXT, sha256 TEXT, PRIMARY KEY(season, week, event))")

    def lock(self, row, inputs, now=None):
        now = now or datetime.now(timezone.utc)
        if row.get("state") != "pre" or now >= timestamp(row["kickoff"]):
            raise LockError("This game has started; bets can only be locked before kickoff.", 409)
        if not row.get("pick"):
            raise LockError("There is no saved prediction to lock for this game yet.", 409)
        text = json.dumps(snapshot(row, inputs), sort_keys=True, allow_nan=False)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        try:
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute("INSERT INTO locks VALUES (?, ?, ?, ?, ?, ?)", (row["season"], row["week"], row["eventId"], now.isoformat(), text, digest))
        except sqlite3.IntegrityError:
            raise LockError("This game is already locked.", 409) from None
        return {"eventId": row["eventId"], "lockedAt": now.isoformat(), "sha256": digest}

    def enrich(self, payload, inputs):
        """Copy, never mutate, the cached feed so a new lock shows up without refetching scores."""
        matchups = payload["queries"]["matchups"]
        period = payload["period"]
        with closing(sqlite3.connect(self.path)) as db:
            saved = {event: (locked_at, text, digest) for event, locked_at, text, digest in
                     db.execute("SELECT event, locked_at, snapshot, sha256 FROM locks WHERE season=? AND week=?", (period["season"], period["week"]))}
        rows = []
        for row in matchups["rows"]:
            row = {**row, "currentQbs": projected_qbs(row, inputs)}
            if row["eventId"] in saved:
                locked_at, text, digest = saved[row["eventId"]]
                locked = json.loads(text)
                row["lock"] = {"lockedAt": locked_at, "sha256": digest, "snapshot": locked,
                               "changes": changes(locked, row, inputs), "result": result(locked, row)}
            rows.append(row)
        return {**payload, "queries": {**payload["queries"], "matchups": {**matchups, "rows": rows}}}
