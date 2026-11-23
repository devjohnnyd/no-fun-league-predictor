import copy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from nfl_predictor.line_tracking import LineTracker
from nfl_predictor.sources import scoreboard_quotes


class LineTrackingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = LineTracker(Path(self.temp.name) / "lines.sqlite3")
        self.game = {"event_id": "1", "home": "BAL", "away": "LAC", "state": "pre", "completed": False,
                     "kickoff": "2026-11-17T01:15:00Z", "total_quotes": [{"line": 42.5, "book": "Book A", "book_id": "A"}]}
        self.row = {"eventId": "1", "homeCode": "BAL", "awayCode": "LAC", "season": 2026, "week": 10,
                    "homeScore": None, "awayScore": None, "totalProjection": None, "forecastIssuedAt": None}
        self.batch = {"issued_at": "2026-11-16T12:00:00Z", "forecast": [{"espn_id": "1", "home": "BAL", "away": "LAC",
                       "total_projection": {"projected_total": 44., "interval_80": [40, 48], "total_samples": [43, 44, 45]}}]}

    def observe(self, at="2026-11-16T13:00:00Z", batches=None, market="marketTotal"):
        payload = {"queries": {"matchups": {"rows": [copy.deepcopy(self.row)]}}}
        manifest = {"retrieved_at": at, "games": [self.game], "scoreboard_source": {"url": "https://example.test/scores", "sha256": "abc"}}
        return self.store.enrich(payload, manifest, [self.batch] if batches is None else batches,
                                 now=datetime.fromisoformat(at.replace("Z", "+00:00")))["queries"]["matchups"]["rows"][0][market]

    def test_movement_and_new_analysis_do_not_rewrite_original_pick(self):
        first = self.observe()
        self.assertEqual(first["originalPick"]["lean"], "Over")
        self.game["total_quotes"][0]["line"] = 45.5
        latest = self.observe("2026-11-16T14:00:00Z")
        self.assertEqual(latest["movement"], 3)
        self.assertEqual(latest["analysis"]["lean"], "Under")
        self.assertEqual(latest["originalPick"]["lean"], "Over")
        self.assertEqual(latest["originalLine"], 42.5)
        self.assertEqual(len(latest["history"]), 2)

    def test_unchanged_background_checks_are_retained_but_do_not_bloat_visible_history(self):
        self.observe()
        self.observe("2026-11-16T13:05:00Z")
        latest = self.observe("2026-11-16T13:10:00Z")
        self.assertEqual(len(self.store.export_rows()),3)
        self.assertEqual(latest["historyObservationCount"],3)
        self.assertEqual([row["observed_at"] for row in latest["history"]],["2026-11-16T13:00:00Z","2026-11-16T13:10:00Z"])
        self.assertEqual(latest["originalIssuedAt"],"2026-11-16T13:00:00Z")

    def test_final_result_uses_saved_line_and_does_not_capture_postgame_quotes(self):
        self.observe()
        self.game.update(state="post", completed=True)
        self.game["total_quotes"][0]["line"] = 99.5
        self.row.update(homeScore=24, awayScore=20)
        result = self.observe("2026-11-17T05:00:00Z")
        self.assertEqual(result["latestLine"], 42.5)
        self.assertEqual(result["actualOutcome"], "Over")
        self.assertTrue(result["correct"])
        self.assertIsNone(result["analysis"])
        self.assertEqual(len(result["history"]), 1)

    def test_new_provider_is_not_reported_as_line_movement(self):
        self.observe()
        self.game["total_quotes"] = [{"line": 50.5, "book": "Book B", "book_id": "B"}]
        result = self.observe("2026-11-16T14:00:00Z")
        self.assertEqual(result["movement"], 0)
        self.assertEqual(result["firstObservedLine"], 50.5)
        self.assertEqual(result["originalLine"], 42.5)

    def test_new_model_reanalysis_retains_first_pick_and_history_survives_restart(self):
        self.observe()
        revised = copy.deepcopy(self.batch)
        revised["issued_at"] = "2026-11-16T13:30:00Z"
        revised["forecast"][0]["total_projection"]["total_samples"] = [30, 31, 32]
        self.store = LineTracker(self.store.path)
        result = self.observe("2026-11-16T14:00:00Z", [self.batch, revised])
        self.assertEqual(result["analysis"]["lean"], "Under")
        self.assertEqual(result["originalPick"]["lean"], "Over")
        self.assertEqual(result["forecastIssuedAt"], revised["issued_at"])

    def test_missing_and_invalid_quotes_do_not_become_zero_lines(self):
        self.game["total_quotes"] = [{"line": None, "book": "Book A", "book_id": "A"}, {"line": 42.25, "book": "Book A", "book_id": "A"}]
        result = self.observe()
        self.assertIsNone(result["latestLine"])
        self.assertIsNone(result["originalPick"])
        self.assertEqual(result["history"], [])

    def test_bootstrap_import_is_idempotent_and_retains_original_pick(self):
        first = self.observe()
        exported = self.store.export_rows()
        other = LineTracker(Path(self.temp.name) / "hosted.sqlite3")
        other.import_rows(exported)
        other.import_rows(exported)
        self.assertEqual(other.export_rows(), exported)
        self.store = other
        self.game["total_quotes"][0]["line"] = 45.5
        latest = self.observe("2026-11-16T14:00:00Z")
        self.assertEqual(latest["originalPick"], first["originalPick"])

    def test_live_score_and_push_stay_separate_from_decisive_results(self):
        self.game["total_quotes"][0]["line"] = 42
        self.observe()
        self.game.update(state="in", completed=False)
        self.row.update(homeScore=21, awayScore=21)
        live = self.observe("2026-11-17T02:00:00Z")
        self.assertIsNone(live["correct"])
        self.game.update(state="post", completed=True)
        final = self.observe("2026-11-17T05:00:00Z")
        self.assertEqual(final["actualOutcome"], "Push")
        self.assertIsNone(final["correct"])

    def test_spread_uses_home_sign_and_settles_at_original_line(self):
        _, spreads = scoreboard_quotes({"odds": [{"provider": {"id": "A", "name": "Book A"}, "spread": 3,
                                                   "pointSpread": {"home": {"close": {"line": "-3"}}}}]})
        self.game["spread_quotes"] = spreads
        self.batch["forecast"][0]["spread_projection"] = {"projected_home_margin": 5., "margin_samples": [4, 5, 6]}
        first = self.observe(market="marketSpread")
        self.assertEqual(first["originalPick"]["lean"], "Home")
        self.assertGreater(first["originalPick"]["push_probability"], 0)
        self.game["spread_quotes"][0]["line"] = "-6.5"
        moved = self.observe("2026-11-16T14:00:00Z", market="marketSpread")
        self.assertEqual(moved["analysis"]["lean"], "Away")
        self.assertEqual(moved["analysis"]["push_probability"], 0)
        self.assertEqual(moved["originalLine"], -3)
        self.assertEqual(moved["movement"], -3.5)
        other = LineTracker(Path(self.temp.name) / "spread-copy.db")
        other.import_rows(self.store.export_rows())
        self.store = other
        self.game.update(state="post", completed=True)
        self.row.update(homeScore=24, awayScore=21)
        final = self.observe("2026-11-17T05:00:00Z", market="marketSpread")
        self.assertEqual(final["actualOutcome"], "Push")
        self.assertIsNone(final["correct"])
        self.assertEqual(final["historyObservationCount"], 2)
        self.assertEqual(len(self.store.original_selections(2026)), 1)

    def test_spread_pick_em_and_late_forecast_do_not_create_retroactive_pick(self):
        self.game["spread_quotes"] = [{"line": "PK", "book": "Book A", "book_id": "A"}]
        self.batch["issued_at"] = "2026-11-16T13:30:00Z"
        self.batch["forecast"][0]["spread_projection"] = {"projected_home_margin": -3., "margin_samples": [-2, -3, -4]}
        first = self.observe(market="marketSpread")
        self.assertEqual(first["latestLine"], 0)
        self.assertIsNone(first["originalPick"])
        fresh = self.observe("2026-11-16T14:00:00Z", market="marketSpread")
        self.assertEqual(fresh["originalPick"]["lean"], "Away")
        self.assertEqual(fresh["originalIssuedAt"], "2026-11-16T14:00:00Z")
