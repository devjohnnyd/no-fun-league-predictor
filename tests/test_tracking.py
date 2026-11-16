import copy
import unittest

from nfl_predictor.tracking import score_batch
from nfl_predictor.sources import games_from_scoreboard


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.batch = {"as_of": "2026-11-10", "forecast": [
            {"espn_id": str(i), "home": "H", "away": "A", "pick": "H", "home_probability": .8}
            for i in range(4)]}
        self.results = {"retrieved_at": "2026-11-16T02:00:00Z", "games": [
            {"event_id": str(i), "home": "H", "away": "A", "kickoff": "2026-11-15T18:00:00Z",
             "completed": i != 2, "home_score": 21 if i == 0 else 14, "away_score": 14}
            for i in range(3)]}

    def test_pending_tie_and_unavailable_are_not_losses(self):
        original = copy.deepcopy(self.batch)
        result = score_batch(self.batch, self.results)
        self.assertEqual(result["metrics"]["games"], 1)
        self.assertEqual(result["metrics"]["correct"], 1)
        self.assertEqual((result["pending"], result["ties"], result["unavailable"]), (1, 1, 1))
        self.assertAlmostEqual(result["metrics"]["brier"], .04)
        self.assertEqual(self.batch, original)

    def test_duplicate_forecasts_and_results_rejected(self):
        self.batch["forecast"].append(self.batch["forecast"][0])
        with self.assertRaises(ValueError):
            score_batch(self.batch, self.results)
        self.batch["forecast"].pop()
        self.results["games"].append(self.results["games"][0])
        with self.assertRaises(ValueError):
            score_batch(self.batch, self.results)

    def test_wrong_team_and_late_issue_rejected(self):
        self.results["games"][0]["home"] = "X"
        with self.assertRaises(ValueError):
            score_batch(self.batch, self.results)
        self.results["games"][0]["home"] = "H"
        self.batch["issued_at"] = "2026-11-15T18:00:00Z"
        with self.assertRaises(ValueError):
            score_batch(self.batch, self.results)

    def test_final_status_is_authoritative(self):
        payload = {"events": [{"id": "1", "date": "2026-11-15T18:00Z", "competitions": [{
            "status": {"type": {"state": "in", "completed": False}}, "competitors": [
                {"homeAway": side, "team": {"id": "1", "abbreviation": side}, "score": "21"}
                for side in ("home", "away")]}]}]}
        game = games_from_scoreboard(payload)[0]
        self.assertFalse(game["completed"])
        self.assertIsNone(game["home_score"])
