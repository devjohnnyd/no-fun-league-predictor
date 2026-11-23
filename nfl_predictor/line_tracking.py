"""Append-only pregame market observations and exact-line model selections."""
from datetime import datetime, timezone
from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3

from .freshness import timestamp
from .totals import line_analysis, spread_analysis, total_forecasts


MARKET_TABLES = {"total": "observations", "spread": "spread_observations"}
OBSERVATION_COLUMNS = "season week event home away book book_id line observed_at url source_sha256 analysis forecast_issued_at".split()


def history_changes(history):
    """Show real changes and each provider's latest check; keep raw rows in SQL."""
    signatures, last, retained = {}, {}, set()
    for index, item in enumerate(history):
        book = item["book_id"]
        signature = (item["line"], item["analysis"], item["forecast_issued_at"])
        if signatures.get(book) != signature:
            retained.add(index)
        signatures[book], last[book] = signature, index
    retained.update(last.values())
    return [item for index, item in enumerate(history) if index in retained]


class LineTracker:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            for table in MARKET_TABLES.values():
                db.execute(f"CREATE TABLE IF NOT EXISTS {table} (season INTEGER, week INTEGER, event TEXT, home TEXT, away TEXT, book TEXT, book_id TEXT, line REAL, observed_at TEXT, url TEXT, source_sha256 TEXT, analysis TEXT, forecast_issued_at TEXT, PRIMARY KEY(season, week, event, book_id, observed_at))")

    def export_rows(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            totals = [dict(row) for row in db.execute("SELECT * FROM observations ORDER BY season, week, event, book_id, observed_at")]
            spreads = [dict(row, market="spread") for row in db.execute("SELECT * FROM spread_observations ORDER BY season, week, event, book_id, observed_at")]
            return totals + spreads

    def original_selections(self, season):
        """Read the first directional pick per game without loading every check."""
        selected, directional = {}, set()
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            for row in db.execute("SELECT * FROM observations WHERE season=? ORDER BY week,event,observed_at,book_id", (season,)):
                key = (row["week"], row["event"])
                if key in directional:
                    continue
                analysis = json.loads(row["analysis"]) if row["analysis"] else None
                if key not in selected:
                    selected[key] = dict(row)
                if analysis and analysis.get("lean") in {"Over", "Under"}:
                    selected[key] = dict(row)
                    directional.add(key)
                elif analysis and not selected[key]["analysis"]:
                    selected[key] = dict(row)
        return list(selected.values())

    def import_rows(self, rows):
        with closing(sqlite3.connect(self.path)) as db, db:
            for row in rows:
                table = MARKET_TABLES[row.get("market", "total")]
                db.execute(f"INSERT OR IGNORE INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [row[key] for key in OBSERVATION_COLUMNS])

    def enrich(self, payload, manifest, batches, now=None):
        now = now or datetime.now(timezone.utc)
        markets = (
            ("total", "marketTotal", "totalProjection", "total_projection", line_analysis, ("Over", "Under")),
            ("spread", "marketSpread", "spreadProjection", "spread_projection", spread_analysis, ("Home", "Away")),
        )
        games = {str(game["event_id"]): game for game in manifest["games"]}
        observed = manifest["retrieved_at"]
        receipt = manifest.get("scoreboard_source", {})
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            for market, field, projection_field, projection_key, analyze, outcomes in markets:
                forecasts = total_forecasts(batches, latest=True, projection_key=projection_key)
                for row in payload["queries"]["matchups"]["rows"]:
                    game = games[row["eventId"]]
                    forecast = forecasts.get(row["eventId"])
                    projection = row.get(projection_field)
                    issued = row.get("forecastIssuedAt") if projection or market == "total" else None
                    if forecast:
                        if (forecast["home"], forecast["away"]) != (row["homeCode"], row["awayCode"]):
                            raise ValueError(f"Market {market} forecast team identity changed")
                        projection, issued = forecast[projection_key], forecast["issued_at"]
                        if timestamp(issued) >= timestamp(game["kickoff"]):
                            raise ValueError(f"Market {market} forecast was issued after kickoff")
                    row[field] = self.track_market(db, market, row, game, observed, receipt, now, projection, issued, analyze, outcomes)
        return payload

    def track_market(self, db, market, row, game, observed, receipt, now, projection, issued, analyze, outcomes):
        table = MARKET_TABLES[market]
        identity = row["season"], row["week"], row["eventId"]
        spread = market == "spread"
        eligible = game["state"] == "pre" and timestamp(observed) <= now < timestamp(game["kickoff"])
        can_analyze = projection and issued and len(issued) > 10 and timestamp(issued) <= timestamp(observed)
        if eligible:
            for quote in game.get(f"{market}_quotes", []):
                line = parse_line(quote["line"], spread)
                if line is None or not quote.get("book"):
                    continue
                analysis = analyze(projection, line) if can_analyze else None
                db.execute(f"INSERT OR IGNORE INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (*identity, row["homeCode"], row["awayCode"], quote["book"], quote["book_id"], line,
                            observed, receipt.get("url"), receipt.get("sha256"), json.dumps(analysis) if analysis else None,
                            issued if analysis else None))
        history = [dict(item) for item in db.execute(f"SELECT * FROM {table} WHERE season=? AND week=? AND event=? ORDER BY observed_at, book_id", identity)]
        for item in history:
            if (item["home"], item["away"]) != (row["homeCode"], row["awayCode"]):
                raise ValueError("Tracked market event identity changed")
            item["analysis"] = json.loads(item["analysis"]) if item["analysis"] else None
        latest = history[-1] if history else None
        first = next(item for item in history if item["book_id"] == latest["book_id"]) if latest else None
        picked = next((item for item in history if item["analysis"] and item["analysis"]["lean"] in outcomes), None)
        original = picked["analysis"] if picked else None
        actual = actual_value = None
        if game.get("completed") and row["homeScore"] is not None and row["awayScore"] is not None:
            actual_value = row["homeScore"] - row["awayScore"] if spread else row["homeScore"] + row["awayScore"]
            if picked:
                threshold = -picked["line"] if spread else picked["line"]
                actual = outcomes[0] if actual_value > threshold else outcomes[1] if actual_value < threshold else "Push"
        current_quote = eligible and latest and latest["observed_at"] == observed
        return {"selectionId": f"{identity[0]}:{identity[1]}:{identity[2]}:market-{market}",
                "firstObservedLine": first["line"] if first else None, "latestLine": latest["line"] if latest else None,
                "movement": latest["line"] - first["line"] if first else None, "book": latest["book"] if latest else None,
                "observedAt": latest["observed_at"] if latest else None, "quoteStatus": "pregame" if current_quote else "last observed pregame" if latest else "unavailable",
                "analysis": latest["analysis"] if current_quote else None, "projection": projection, "forecastIssuedAt": issued,
                "originalPick": original, "originalLine": picked["line"] if picked else None,
                "originalIssuedAt": picked["observed_at"] if picked else None,
                "actualMargin" if spread else "actualTotal": actual_value, "actualOutcome": actual,
                "correct": original["lean"] == actual if original and actual in outcomes else None,
                "historyObservationCount": len(history), "history": history_changes(history)}


def parse_line(value, spread):
    if isinstance(value, bool):
        return None
    if spread and isinstance(value, str):
        value = value.strip().upper().replace("−", "-")
        if value in {"PK", "PICK", "PICK'EM"}:
            value = 0
    try:
        line = float(value)
    except (TypeError, ValueError):
        return None
    if math.isfinite(line) and (line * 2).is_integer() and (-100 < line < 100 if spread else 0 < line < 150):
        return line
    return None
