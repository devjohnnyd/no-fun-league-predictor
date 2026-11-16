import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from nfl_predictor.dashboard import week_payload
from nfl_predictor.server import WeekFeed
from nfl_predictor.sources import games_from_scoreboard
from nfl_predictor.storage import read_json

ROOT = Path(__file__).resolve().parents[1]


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata = read_json(ROOT / "data/snapshots/venues-v4-2026-11-15.json")
        cls.batch = read_json(ROOT / "archive/session-2026-11-10/enhanced/model.json")
        cls.manifest = read_json(ROOT / "data/snapshots/week10-results-2026-11-16T0155Z.json")

    def test_full_week_and_original_record_are_preserved(self):
        rows = week_payload(self.manifest, self.metadata, [self.batch])["queries"]["matchups"]["rows"]
        self.assertEqual(len(rows), 14)
        self.assertEqual(sum(r["originalCorrect"] is True for r in rows), 8)
        self.assertEqual(sum(r["originalCorrect"] is False for r in rows), 3)
        self.assertEqual(sum(r["pick"] is None for r in rows), 1)

    def test_score_refresh_does_not_rewrite_the_original_pick(self):
        later = copy.deepcopy(self.batch)
        later["issued_at"] = "2026-11-11T12:00:00Z"
        first = later["forecast"][0]
        first["home_probability"] = 1 - first["home_probability"]
        first["pick"] = first["home"] if first["home_probability"] >= .5 else first["away"]
        result = week_payload(self.manifest, self.metadata, [self.batch, later])
        row = next(r for r in result["queries"]["matchups"]["rows"] if r["eventId"] == first["espn_id"])
        self.assertNotEqual(row["homeProbability"], row["originalHomeProbability"])
        self.assertEqual(row["originalCorrect"], True)

    def test_backdated_forecasts_cannot_be_displayed(self):
        changed = copy.deepcopy(self.batch)
        changed["issued_at"] = "2026-11-17T12:00:00Z"
        with self.assertRaises(ValueError):
            week_payload(self.manifest, self.metadata, [changed])

    def test_live_feed_cache_is_bounded_and_errors_do_not_fake_freshness(self):
        feed = WeekFeed(2026, 10, self.metadata, [self.batch], ttl=30)
        with patch("nfl_predictor.server.fetch_week", return_value=self.manifest) as fetch:
            first, second = feed.get(), feed.get()
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(first["generatedAt"], second["generatedAt"])
        feed.updated = 0
        with patch("nfl_predictor.server.fetch_week", side_effect=RuntimeError("Unavailable")):
            with self.assertRaises(RuntimeError):
                feed.get()
        self.assertEqual(feed.cached["generatedAt"], self.manifest["retrieved_at"])

    def test_completed_game_without_scores_is_rejected(self):
        payload = {"events": [{"id": "1", "date": "2026-11-15T18:00Z", "competitions": [{
            "status": {"type": {"state": "post", "completed": True}}, "competitors": [
                {"homeAway": side, "team": {"id": "1", "abbreviation": side}}
                for side in ("home", "away")]}]}]}
        with self.assertRaises(ValueError):
            games_from_scoreboard(payload)

    def test_first_partial_feed_is_rejected_against_saved_forecasts(self):
        partial = {**self.manifest, "games": self.manifest["games"][:1]}
        feed = WeekFeed(2026, 10, self.metadata, [self.batch])
        with patch("nfl_predictor.server.fetch_week", return_value=partial):
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                feed.get()
        self.assertIsNone(feed.cached)

    def test_schedule_requires_unforecasted_thursday_game_on_first_fetch(self):
        dataset = read_json(ROOT / "data/snapshots/dataset-v4-2026-11-16.json.gz")
        partial = {**self.manifest, "games": [g for g in self.manifest["games"] if g["slate_eligible"]]}
        feed = WeekFeed(2026, 10, self.metadata, [self.batch], dataset)
        with patch("nfl_predictor.server.fetch_week", return_value=partial):
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                feed.get()

    def test_forecast_only_feed_recovers_when_unforecasted_game_returns(self):
        feed = WeekFeed(2026, 10, self.metadata, [self.batch])
        partial = {**self.manifest, "games": [g for g in self.manifest["games"] if g["slate_eligible"]]}
        with patch("nfl_predictor.server.fetch_week", return_value=partial):
            feed.get()
        feed.updated = 0
        with patch("nfl_predictor.server.fetch_week", return_value=self.manifest):
            full = feed.get()
        self.assertEqual(len(full["queries"]["matchups"]["rows"]), 14)
        feed.updated = 0
        with patch("nfl_predictor.server.fetch_week", return_value=partial):
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                feed.get()
        self.assertIs(feed.cached, full)

    def test_partial_refresh_retains_complete_cache_and_can_recover(self):
        feed = WeekFeed(2026, 10, self.metadata, [self.batch])
        with patch("nfl_predictor.server.fetch_week", return_value=self.manifest):
            complete = feed.get()
        feed.updated = 0
        partial = {**self.manifest, "games": [g for g in self.manifest["games"] if g["slate_eligible"]]}
        with patch("nfl_predictor.server.fetch_week", return_value=partial):
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                feed.get()
        self.assertIs(feed.cached, complete)
        self.assertEqual(feed.cached["generatedAt"], self.manifest["retrieved_at"])
        recovered = {**self.manifest, "retrieved_at": "2026-11-16T14:00:00Z"}
        with patch("nfl_predictor.server.fetch_week", return_value=recovered):
            latest = feed.get()
        self.assertEqual(len(latest["queries"]["matchups"]["rows"]), 14)
        self.assertEqual(latest["generatedAt"], recovered["retrieved_at"])

    def test_refresh_rejects_changed_identity_on_unforecasted_game(self):
        feed = WeekFeed(2026, 10, self.metadata, [self.batch])
        with patch("nfl_predictor.server.fetch_week", return_value=self.manifest):
            complete = feed.get()
        changed = copy.deepcopy(self.manifest)
        next(g for g in changed["games"] if not g["slate_eligible"])["home"] = "BAL"
        feed.updated = 0
        with patch("nfl_predictor.server.fetch_week", return_value=changed):
            with self.assertRaisesRegex(ValueError, "identity"):
                feed.get()
        self.assertIs(feed.cached, complete)
