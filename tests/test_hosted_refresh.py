from copy import deepcopy
import unittest

from nfl_predictor.dataset import replace_season


class HostedRefreshTests(unittest.TestCase):
    def test_current_season_replacement_retains_historical_data_and_receipts(self):
        keys = ("schedule", "team_games", "qb_games", "snaps", "injuries", "ngs", "kicks")
        historical = {key: [{"season": 2025, "value": "past"}, {"season": 2026, "value": "old"}] for key in keys}
        historical.update(created_at="old", players=["old-player"], sources=[{"retrieved_at": "earlier"}], quality={"old": True})
        current = {key: [{"season": 2026, "value": "fresh"}] for key in keys}
        current.update(created_at="new", players=["new-player"], sources=[{"retrieved_at": "today"}], quality={"fresh": True})
        historical["snaps"] = [["2025_01_A_B", "A", "past"], ["2026_01_A_B", "A", "old"]]
        current["snaps"] = [["2026_01_A_B", "A", "fresh"]]
        historical["kicks"] = [{"game_id": "2025_01_A_B", "value": "past"}, {"game_id": "2026_01_A_B", "value": "old"}]
        current["kicks"] = [{"game_id": "2026_01_A_B", "value": "fresh"}]
        before = deepcopy(historical)
        result = replace_season(historical, current, 2026)
        for key in set(keys) - {"snaps", "kicks"}:
            self.assertEqual(result[key], [{"season": 2025, "value": "past"}, {"season": 2026, "value": "fresh"}])
        self.assertEqual(result["snaps"], [["2025_01_A_B", "A", "past"], ["2026_01_A_B", "A", "fresh"]])
        self.assertEqual(result["kicks"], [{"game_id": "2025_01_A_B", "value": "past"}, {"game_id": "2026_01_A_B", "value": "fresh"}])
        self.assertEqual(result["sources"], [{"retrieved_at": "earlier"}, {"retrieved_at": "today"}])
        self.assertEqual(historical, before)


class VisitRefreshTests(unittest.TestCase):
    def setUp(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from unittest.mock import Mock
        self.UTC, self.datetime = timezone.utc, datetime
        self.dataset = {"schedule": [{"season": 2026, "week": 10, "gameday": "2026-11-16", "gametime": "20:15"},
                                     {"season": 2026, "week": 11, "gameday": "2026-11-19", "gametime": "20:15"},
                                     {"season": 2026, "week": 11, "gameday": "2026-11-23", "gametime": "20:15"},
                                     {"season": 2026, "week": 19, "gameday": "2027-01-10", "gametime": "13:00"}]}
        self.refresh = SimpleNamespace(status={"state": "idle"}, cached_models=Mock(return_value="models"),
                                       start=Mock(return_value={"state": "running"}))
        from nfl_predictor.server import SeasonFeeds
        self.feeds = SeasonFeeds.__new__(SeasonFeeds)
        self.feeds.dataset, self.feeds.season, self.feeds.refresh = self.dataset, 2026, self.refresh

    def at(self, text):
        return self.datetime.fromisoformat(text).replace(tzinfo=self.UTC)

    def test_current_week_rolls_over_at_six_am_eastern_tuesday(self):
        from nfl_predictor.server import current_week
        self.assertEqual(current_week(self.dataset, 2026, self.at("2026-11-17T10:59")), 10)
        self.assertEqual(current_week(self.dataset, 2026, self.at("2026-11-17T11:00")), 11)
        self.assertEqual(current_week(self.dataset, 2026, self.at("2026-11-24T11:00")), 11)
        self.assertEqual(current_week({"schedule": []}, 2026), 1)

    def test_visits_start_a_context_check_only_when_stale_and_useful(self):
        now = self.at("2026-11-20T12:00")
        self.assertIsNone(self.feeds.refresh_if_stale(10, now))
        self.refresh.status = {"state": "complete", "week": 11, "completedAt": "2026-11-20T11:00:00+00:00"}
        self.assertIsNone(self.feeds.refresh_if_stale(11, now))
        self.refresh.status = {"state": "running", "week": 11}
        self.assertIsNone(self.feeds.refresh_if_stale(11, now))
        self.refresh.status = {"state": "complete", "week": 11, "completedAt": "2026-11-20T09:00:00+00:00"}
        self.refresh.cached_models.return_value = None
        self.assertIsNone(self.feeds.refresh_if_stale(11, now))
        self.refresh.start.assert_not_called()
        self.refresh.cached_models.return_value = "models"
        self.assertEqual(self.feeds.refresh_if_stale(11, now)["state"], "running")
        self.refresh.start.assert_called_once_with(11, mode="context")
        self.assertIsNone(self.feeds.refresh_if_stale(11, self.at("2026-11-24T02:00")))
