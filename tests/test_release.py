"""Exercise release boundaries without network or fitting a second model."""
import copy
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

from nfl_predictor.forecast import issue
from nfl_predictor.storage import sha256, write_new


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
        self.dataset, self.venues = self.root / "dataset.json", self.root / "venues.json"
        write_new(self.dataset, {"schedule": [], "attribution": []})
        write_new(self.venues, {})
        sources = {name: {"status": "ok", "url": "https://example.org/" + name,
                            "event_id": "1", "retrieved_at": self.now.isoformat()}
                   for name in ("stats", "injuries", "depth", "weather", "staff")}
        sources["stats"].update(season=2026, through_week=9)
        sources["weather"].update(valid_at="2026-11-17T01:00:00Z", temperature_f=50, wind_mph=5)
        game = {"event_id": "1", "home": "BAL", "away": "LAC", "season": 2026,
                "week": 10, "state": "pre", "kickoff": "2026-11-17T01:15:00Z", "sources": sources}
        self.prepared = {"season": 2026, "week": 10, "dataset_sha256": sha256(self.dataset),
            "venues_sha256": sha256(self.venues), "statistics_coverage": {"complete": True},
            "games": [{"event_id": "1", "game_id": "test", "game": game, "schedule": {},
                       "context": {"teams": {"BAL": {"qb_status": "Projected"}, "LAC": {"qb_status": "Projected"}}},
                       "features": {"metric": 1}, "feature_built_at": self.now.isoformat()}]}
        self.report = {"source_sha256": {"dataset": sha256(self.dataset), "venues": sha256(self.venues)},
            "models": {name: {"training_cutoff": {"season": 2026, "before_week": 10}}
                       for name in ("v2_baseline", "body_clock")}}
        write_new(self.root / "summary-1.json", {})
        engine = type("Engine", (), {"dataset": {"attribution": []}, "features": lambda *_: (
            {"metric": 1}, {"home_qb": "Home QB", "away_qb": "Away QB"})})()
        self.patches = [patch("nfl_predictor.forecast.FeatureEngine", return_value=engine),
                        patch("nfl_predictor.forecast.model_probabilities", return_value=np.array([.65])),
                        patch("nfl_predictor.forecast.contributions", return_value=[]),
                        patch("nfl_predictor.forecast.elo_probability", return_value=.55)]
        for mock in self.patches:
            mock.start()
            self.addCleanup(mock.stop)

    def release(self, final=False):
        write_new(self.root / "prepared.json", self.prepared)
        write_new(self.root / "research.json", self.report)
        return issue(self.dataset, self.venues, self.root / "research.json", self.root / "prepared.json",
                     self.root / "output", final=final, now=self.now, verify_live=False)

    def test_fresh_pregame_release_preserves_shadow_and_exact_time(self):
        result = self.release()
        self.assertEqual(result["issued_at"], self.now.isoformat())
        self.assertEqual(result["forecast"][0]["pick"], "BAL")
        self.assertEqual(result["forecast"][0]["shadow_forecasts"][0]["model"], "body_clock")
        self.assertTrue((self.root / "output/forecast.json").is_file())
        with self.assertRaises(FileExistsError):
            issue(self.dataset, self.venues, self.root / "research.json", self.root / "prepared.json", self.root / "output")

    def test_stale_feature_vector_produces_blocked_record(self):
        self.prepared["games"][0]["feature_built_at"] = "2026-11-16T11:00:00Z"
        result = self.release()
        self.assertEqual(result["forecast"], [])
        self.assertTrue((self.root / "output/blocked.json").is_file())
        self.assertIn("too old", " ".join(result["blocked"][0]["reasons"]))

    def test_started_game_is_rejected(self):
        self.prepared["games"][0]["game"]["state"] = "in"
        self.assertFalse(self.release()["forecast"])

    def test_model_must_stop_before_target_week(self):
        self.report["models"]["v2_baseline"]["training_cutoff"]["before_week"] = 11
        self.assertFalse(self.release()["forecast"])

    def test_incomplete_previous_week_coverage_blocks(self):
        self.prepared["statistics_coverage"]["complete"] = False
        self.assertFalse(self.release()["forecast"])

    def test_changed_feature_vector_blocks(self):
        self.prepared["games"][0]["features"]["metric"] = 999
        self.assertFalse(self.release()["forecast"])

    def test_dataset_hash_mismatch_fails_before_release(self):
        self.prepared["dataset_sha256"] = "tampered"
        with self.assertRaisesRegex(ValueError, "Dataset differs"):
            self.release()

    def test_final_requires_official_inactives_for_both_teams(self):
        self.now = datetime(2026, 11, 17, 0, tzinfo=timezone.utc)
        self.prepared["games"][0]["feature_built_at"] = self.now.isoformat()
        for source in self.prepared["games"][0]["game"]["sources"].values():
            source["retrieved_at"] = self.now.isoformat()
        result = self.release(final=True)
        self.assertFalse(result["forecast"])
        self.assertIn("inactives", " ".join(result["blocked"][0]["reasons"]))


if __name__ == "__main__":
    unittest.main()
