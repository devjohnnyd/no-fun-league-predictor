import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta, timezone

from nfl_predictor.refresh_job import AnalysisRefresh, SCORE_MODELS_VERSION
from nfl_predictor.storage import read_json, sha256, write_new


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
                 patch("nfl_predictor.live.prepare", return_value={"games": [{"event_id":"Thursday", "game":{"event_id":"Thursday","kickoff":"2099-01-01T00:00:00Z","state":"pre"}, "features": {}}]}), \
                 patch("nfl_predictor.research.research"), patch("nfl_predictor.totals.research_totals"), \
                 patch("nfl_predictor.refresh_job.sha256", return_value="digest"), \
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

    def test_recent_models_reuse_exact_artifacts_and_expire_or_reject_tampering(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            venues = root / "venues.json"
            write_new(venues, {})
            manager = SimpleNamespace(season=2026, metadata_path=venues)
            job = AnalysisRefresh(manager, [], root / "refreshes")
            model = job.output / "one"
            for name in ("dataset.json.gz", "research/research.json", "totals/totals-model.json"):
                write_new(model / name, {"test": True})
            now = datetime.now(timezone.utc)
            write_new(model / "models-ready.json", {"season":2026,"week":11,"createdAt":now.isoformat(),"venues_sha256":sha256(venues),"scoreModelsVersion":SCORE_MODELS_VERSION,
                "files":{name:sha256(model/name) for name in ("dataset.json.gz", "research/research.json", "totals/totals-model.json")}})
            self.assertEqual(job.cached_models(11, now), model)
            self.assertIsNone(job.cached_models(10, now))
            self.assertIsNone(job.cached_models(11, now + timedelta(hours=24)))
            (model / "research/research.json").write_text("tampered")
            self.assertIsNone(job.cached_models(11, now))

    def test_context_check_does_not_download_or_refit_and_keeps_final_scope(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            feed = Mock(card_path=None)
            manager = SimpleNamespace(season=2026, metadata={}, metadata_path=root/"venues", staff_seed=root/"staff", dataset={"historical":True},
                                      feed=Mock(return_value=feed), install=Mock())
            job = AnalysisRefresh(manager, [], root / "refreshes")
            model = job.output / "models"
            write_new(model / "dataset.json.gz", {"original":True})
            batch = {"forecast":[{}],"blocked":[]}
            with patch.object(job, "cached_models", return_value=model), patch("nfl_predictor.acquire.acquire") as download, \
                 patch("nfl_predictor.engine.FeatureEngine"), patch("nfl_predictor.live.coverage", return_value={"complete":True}), \
                 patch("nfl_predictor.live.prepare", return_value={"games":[{"features":{}}]}) as prepare, \
                 patch("nfl_predictor.research.research") as fit, patch("nfl_predictor.forecast.issue", return_value=batch) as issue:
                job.run(11, mode="context", event_ids=["123"], final=True)
            self.assertEqual(job.status["state"], "complete")
            download.assert_not_called()
            fit.assert_not_called()
            self.assertEqual(prepare.call_args.kwargs["event_ids"], {"123"})
            self.assertTrue(issue.call_args.kwargs["final"])
            pointer = read_json(next(job.output.glob("*/dataset-reference.json")))
            self.assertEqual(pointer["path"], "models/dataset.json.gz" if "/" in pointer["path"] else "models\\dataset.json.gz")
            self.assertEqual(pointer["sha256"], sha256(model / "dataset.json.gz"))

    def test_full_budget_is_shared_and_survives_a_new_manager(self):
        with TemporaryDirectory() as folder, patch("nfl_predictor.refresh_job.threading.Thread"):
            first = AnalysisRefresh(Mock(), [], Path(folder)/"refreshes")
            self.assertEqual(first.start(11)["state"], "running")
            second = AnalysisRefresh(Mock(), [], Path(folder)/"refreshes")
            self.assertEqual(second.start(11)["state"], "blocked")
            self.assertEqual(read_json(Path(folder)/"refresh-budget.json")["count"], 1)

    def test_manual_runs_cannot_exhaust_the_scheduled_budget(self):
        with TemporaryDirectory() as folder, patch("nfl_predictor.refresh_job.threading.Thread"):
            budget = Path(folder)/"refresh-budget.json"
            today = datetime.now(timezone.utc).date().isoformat()
            budget.write_text(json.dumps({"date": today, "count": 0, "manual": 4, "last_started": 0}), encoding="utf-8")
            job = AnalysisRefresh(Mock(), [], Path(folder)/"refreshes")
            self.assertIn("4 manual", job.start(11, manual=True)["message"])
            self.assertEqual(job.start(11)["state"], "running")
            self.assertEqual(read_json(budget)["count"], 1)
            self.assertEqual(read_json(budget)["manual"], 4)
