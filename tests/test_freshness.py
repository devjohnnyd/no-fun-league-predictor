import copy
from datetime import datetime, timezone
import unittest

from nfl_predictor.freshness import REQUIRED, check_pregame, timestamp


class PregameTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 16, 23, 45, tzinfo=timezone.utc)
        self.game = {"event_id": "1", "season": 2026, "week": 10, "home": "BAL", "away": "LAC",
                     "state": "pre", "kickoff": "2026-11-17T01:15:00Z", "sources": {}}
        for kind in list(REQUIRED) + ["inactives"]:
            self.game["sources"][kind] = {"url": "https://example.org/evidence", "status": "ok", "event_id": "1",
                "retrieved_at": "2026-11-16T23:40:00Z", "through_week": 9, "season": 2026,
                "valid_at": "2026-11-17T01:00:00Z", "temperature_f": 40, "wind_mph": 10,
                "official": True, "verified_teams": ["BAL", "LAC"]}

    def check(self, final=False):
        return check_pregame(self.game, self.now, final)

    def test_current_context_is_ready_and_stale_context_is_not(self):
        self.assertTrue(self.check()["ready"])
        self.game["sources"]["injuries"]["retrieved_at"] = "2026-11-10T12:00:00Z"
        self.assertFalse(self.check()["ready"])

    def test_no_late_forecasts(self):
        self.game["kickoff"] = self.now.isoformat()
        self.assertFalse(self.check()["ready"])
        self.game["state"] = "in"
        self.assertFalse(self.check()["ready"])

    def test_final_requires_official_inactive_lists_for_both_teams(self):
        self.assertTrue(self.check(final=True)["ready"])
        self.game["sources"]["inactives"]["verified_teams"] = ["BAL"]
        self.assertFalse(self.check(final=True)["ready"])

    def test_missing_weather_cannot_silently_be_calm(self):
        del self.game["sources"]["weather"]["wind_mph"]
        self.assertFalse(self.check()["ready"])
        self.game["sources"]["weather"]["enclosed_verified"] = True
        self.assertTrue(self.check()["ready"])

    def test_cross_game_and_future_data_are_rejected(self):
        self.game["sources"]["stats"]["event_id"] = "other"
        self.assertFalse(self.check()["ready"])
        self.game["sources"]["stats"]["event_id"] = "1"
        self.game["sources"]["stats"]["through_week"] = 10
        self.assertFalse(self.check()["ready"])

    def test_future_time_and_naive_time_rejected(self):
        self.game["sources"]["depth"]["retrieved_at"] = "2026-11-17T00:00:00Z"
        self.assertFalse(self.check()["ready"])
        with self.assertRaises(ValueError):
            timestamp("2026-11-16T12:00:00")

    def test_scope_season_mismatch_rejected(self):
        self.game["sources"]["stats"]["season"] = 2025
        self.assertFalse(self.check()["ready"])
