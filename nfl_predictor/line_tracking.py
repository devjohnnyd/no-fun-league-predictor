"""Append-only pregame market observations and exact-line model selections."""
from datetime import datetime, timezone
from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3

from .freshness import timestamp
from .totals import line_analysis, total_forecasts


class LineTracker:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS observations (season INTEGER, week INTEGER, event TEXT, home TEXT, away TEXT, book TEXT, book_id TEXT, line REAL, observed_at TEXT, url TEXT, source_sha256 TEXT, analysis TEXT, forecast_issued_at TEXT, PRIMARY KEY(season, week, event, book_id, observed_at))")

    def enrich(self, payload, manifest, batches, now=None):
        now = now or datetime.now(timezone.utc)
        forecasts = total_forecasts(batches, latest=True)
        games = {str(game["event_id"]): game for game in manifest["games"]}
        observed = manifest["retrieved_at"]
        receipt = manifest.get("scoreboard_source", {})
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            for row in payload["queries"]["matchups"]["rows"]:
                game = games[row["eventId"]]
                forecast = forecasts.get(row["eventId"])
                # Latest analysis may change; the first tracked pick remains in SQLite.
                projection = row.get("totalProjection")
                issued = row.get("forecastIssuedAt")
                if forecast:
                    if (forecast["home"], forecast["away"]) != (row["homeCode"], row["awayCode"]):
                        raise ValueError("Market total forecast team identity changed")
                    projection, issued = forecast["total_projection"], forecast["issued_at"]
                    if timestamp(issued) >= timestamp(game["kickoff"]):
                        raise ValueError("Market total forecast was issued after kickoff")
                eligible = game["state"] == "pre" and timestamp(observed) <= now < timestamp(game["kickoff"])
                if eligible:
                    for quote in game.get("total_quotes", []):
                        try:
                            line = float(quote["line"])
                            if not math.isfinite(line) or not 0 < line < 150 or not (line * 2).is_integer() or not quote.get("book"):
                                continue
                        except (TypeError, ValueError):
                            continue
                        analysis = line_analysis(projection, line) if projection and issued and len(issued) > 10 and timestamp(issued) <= timestamp(observed) else None
                        db.execute("INSERT OR IGNORE INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                   (row["season"], row["week"], row["eventId"], row["homeCode"], row["awayCode"], quote["book"], quote["book_id"], line,
                                    observed, receipt.get("url"), receipt.get("sha256"), json.dumps(analysis) if analysis else None, issued if analysis else None))
                history = [dict(item) for item in db.execute("SELECT * FROM observations WHERE season=? AND week=? AND event=? ORDER BY observed_at, book_id",
                                                           (row["season"], row["week"], row["eventId"]))]
                if any((item["home"], item["away"]) != (row["homeCode"], row["awayCode"]) for item in history):
                    raise ValueError("Tracked market event identity changed")
                latest = history[-1] if history else None
                same_book = [item for item in history if item["book_id"] == latest["book_id"]] if latest else []
                first = same_book[0] if same_book else None
                picked = next((item for item in history if item["analysis"] and json.loads(item["analysis"])["lean"] != "Even"), None)
                original = json.loads(picked["analysis"]) if picked else None
                total = row["homeScore"] + row["awayScore"] if row["homeScore"] is not None and row["awayScore"] is not None else None
                actual = ("Over" if total > picked["line"] else "Under" if total < picked["line"] else "Push") if picked and game.get("completed") and total is not None else None
                latest_analysis = line_analysis(projection, latest["line"]) if eligible and projection and issued and len(issued) > 10 and timestamp(issued) <= timestamp(observed) and latest else None
                row["marketTotal"] = {"selectionId": f"{row['season']}:{row['week']}:{row['eventId']}:market-total",
                    "firstObservedLine": first["line"] if first else None, "latestLine": latest["line"] if latest else None,
                    "movement": latest["line"] - first["line"] if first else None, "book": latest["book"] if latest else None,
                    "observedAt": latest["observed_at"] if latest else None, "quoteStatus": "pregame" if eligible and latest and latest["observed_at"] == observed else "last observed pregame" if latest else "unavailable",
                    "analysis": latest_analysis, "projection": projection, "forecastIssuedAt": issued,
                    "originalPick": original, "originalLine": picked["line"] if picked else None,
                    "originalIssuedAt": picked["observed_at"] if picked else None,
                    "actualTotal": total if game.get("completed") else None, "actualOutcome": actual,
                    "correct": original["lean"] == actual if original and actual in {"Over", "Under"} else None,
                    "history": [{**item, "analysis": json.loads(item["analysis"]) if item["analysis"] else None} for item in history]}
        return payload
