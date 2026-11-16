import copy
import unittest

from nfl_predictor.experiments import score_experiments
from nfl_predictor.market import aligned_consensus


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.batch = {"issued_at": "2026-11-16T12:00:00Z", "forecast": [
            {"espn_id": str(i), "home": "BAL", "away": "LAC", "home_probability": .6,
             "shadow_forecasts": [{"model": "new", "home_probability": .8}] if i == 1 else []}
            for i in (1, 2)]}
        self.results = {"games": [{"event_id": str(i), "home": "BAL", "away": "LAC", "completed": True,
            "kickoff": "2026-11-17T01:15:00Z", "home_score": 24 if i == 1 else 17, "away_score": 20} for i in (1, 2)]}

    def test_each_candidate_is_compared_on_identical_games(self):
        result = score_experiments(self.batch, self.results)["models"][0]
        self.assertEqual(result["coverage"], "1 of 2 decisive primary forecasts")
        self.assertEqual(result["primary_same_games"]["correct"], 1)
        self.assertAlmostEqual(result["delta_brier"], -.12)

    def test_missing_exact_issue_time_cannot_count_as_prospective(self):
        self.batch.pop("issued_at")
        with self.assertRaises(ValueError):
            score_experiments(self.batch, self.results)

    def test_ties_and_pending_results_are_excluded(self):
        self.results["games"][0]["home_score"] = 20
        self.results["games"][1]["completed"] = False
        self.assertEqual(score_experiments(self.batch, self.results)["models"], [])

    def test_repeated_book_quotes_do_not_gain_extra_weight(self):
        common = {"event_id": "1", "home_price": -110, "away_price": -110, "observed_at": "2026-11-16T11:59:00Z"}
        quotes = [{**common, "book": "A"}, {**common, "book": "A", "observed_at": "2026-11-16T11:58:00Z", "home_price": -500}, {**common, "book": "B"}]
        result = aligned_consensus(quotes, self.batch["issued_at"], "2026-11-17T01:15:00Z")
        self.assertEqual(result["books"], 2)
        self.assertEqual(result["home_probability"], .5)
