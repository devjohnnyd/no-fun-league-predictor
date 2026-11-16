from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from nfl_predictor.refresh_job import AnalysisRefresh


class AnalysisRefreshTests(unittest.TestCase):
    def test_incomplete_previous_week_preserves_models_and_skips_release(self):
        with TemporaryDirectory() as folder:
            feed = Mock(card_path=None)
            manager = SimpleNamespace(feed=Mock(return_value=feed), season=2026, metadata={}, metadata_path=Path("venues.json"), install=Mock())
            job = AnalysisRefresh(manager, [Path("history")], folder)
            with patch("nfl_predictor.acquire.acquire"), patch("nfl_predictor.dataset.build_dataset", return_value={}), \
                 patch("nfl_predictor.engine.FeatureEngine"), patch("nfl_predictor.live.coverage", return_value={"complete": False, "missing_games": ["Monday"]}), \
                 patch("nfl_predictor.forecast.issue") as release:
                job.run(11)
            self.assertEqual(job.status["state"], "blocked")
            self.assertIn("1 prior game", job.status["message"])
            manager.install.assert_not_called()
            release.assert_not_called()
            feed.get.assert_called_once()

    def test_success_installs_a_new_batch_after_all_refresh_steps(self):
        with TemporaryDirectory() as folder:
            feed = Mock(card_path=None)
            manager = SimpleNamespace(feed=Mock(return_value=feed), season=2026, metadata={}, metadata_path=Path("venues.json"), staff_seed=Path("seed.json"), install=Mock())
            job = AnalysisRefresh(manager, [Path("history")], folder)
            batch = {"forecast": [{"espn_id": "Thursday"}], "blocked": []}
            with patch("nfl_predictor.acquire.acquire"), patch("nfl_predictor.dataset.build_dataset", return_value={"fresh": True}), \
                 patch("nfl_predictor.engine.FeatureEngine"), patch("nfl_predictor.live.coverage", return_value={"complete": True}), \
                 patch("nfl_predictor.live.prepare", return_value={"games": [{"features": {}}]}), \
                 patch("nfl_predictor.research.research"), patch("nfl_predictor.totals.research_totals"), \
                 patch("nfl_predictor.forecast.issue", return_value=batch):
                job.run(10)
            self.assertEqual(job.status["state"], "complete")
            self.assertEqual(manager.install.call_args.args[:2], ({"fresh": True}, batch))

    def test_an_existing_job_is_not_started_twice(self):
        job = AnalysisRefresh(Mock(), [], "unused")
        job.status = {"state": "running", "week": 10, "message": "Working"}
        with patch("nfl_predictor.refresh_job.threading.Thread") as thread:
            self.assertEqual(job.start(11)["week"], 10)
            thread.assert_not_called()
