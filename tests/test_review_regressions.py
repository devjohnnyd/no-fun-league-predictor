"""Regression coverage for F2 availability and F4 season-start research."""
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

from nfl_predictor.engine import FeatureEngine
from nfl_predictor.research import research, rolling
from nfl_predictor.storage import clean, read_json
from nfl_predictor.totals import research_totals, rolling_totals

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/snapshots/dataset-v4-2026-11-16.json.gz"
VENUES = ROOT / "data/snapshots/venues-v4-2026-11-15.json"


class AvailabilityRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.venues = read_json(DATA), read_json(VENUES)
        cls.entry = read_json(ROOT / "reports/2026-11-16-complete/pregame-totals/prepared.json")["games"][0]

    def setUp(self):
        self.engine = FeatureEngine(self.data, self.venues)
        self.context = copy.deepcopy(self.entry["context"])
        for team in self.context["teams"].values():
            team["injuries"] = []

    def test_both_questionable_starting_qbs_use_their_backups(self):
        for team in self.context["teams"].values():
            team["injuries"] = [{"pid": team["qb_id"], "position": "QB", "status": "Questionable"}]
        base, _ = self.engine.features(self.entry["schedule"], self.context)
        changed, detail = self.engine.features(self.entry["schedule"], self.context, "questionable_out")
        for side in ("home", "away"):
            team = self.context["teams"][self.entry["game"][side]]
            self.assertEqual(detail[side + "_qb"]["id"], team["backup_qb_id"])
        self.assertNotEqual(base["qb_epa_diff"], changed["qb_epa_diff"])

    def test_questionable_qb_without_verified_backup_is_unavailable(self):
        home = self.context["teams"][self.entry["game"]["home"]]
        home["injuries"] = [{"pid": home["qb_id"], "position": "QB", "status": "Questionable"}]
        home["backup_qb_id"] = None
        with self.assertRaisesRegex(ValueError, "available verified backup"):
            self.engine.features(self.entry["schedule"], self.context, "questionable_out")

    def test_questionable_backup_cannot_replace_questionable_starter(self):
        home = self.context["teams"][self.entry["game"]["home"]]
        home["injuries"] = [{"pid": pid, "position": "QB", "status": "Questionable"}
                            for pid in (home["qb_id"], home["backup_qb_id"])]
        with self.assertRaisesRegex(ValueError, "available verified backup"):
            self.engine.features(self.entry["schedule"], self.context, "questionable_out")

    def test_healthy_qb_scenario_does_not_change_baseline(self):
        base, _ = self.engine.features(self.entry["schedule"], self.context)
        changed, _ = self.engine.features(self.entry["schedule"], self.context, "questionable_out")
        self.assertEqual(clean(base), clean(changed))


class SeasonStartRegressionTests(unittest.TestCase):
    def test_week_one_winner_model_is_saved_without_current_season_diagnostics(self):
        frame = pd.read_csv(ROOT / "reports/2026-11-16-complete/features.csv")
        with TemporaryDirectory() as directory, patch("nfl_predictor.research.feature_frame", return_value=frame), \
                patch("nfl_predictor.research.BASE_NAMES", ["off_epa_diff"]), patch("nfl_predictor.research.FAMILIES", {}):
            output = Path(directory) / "research"
            result = research(DATA, output, 2026, 1, VENUES)
            self.assertTrue((output / "research.json").is_file())
        model = result["models"]["v2_baseline"]
        self.assertEqual(model["training_cutoff"], {"season": 2026, "before_week": 1})
        self.assertEqual(model["training_games"], len(frame[frame.season.lt(2026) & frame.target.isin([0, 1])]))
        self.assertTrue(all(row["games"] == 0 and row["brier"] is None for row in result["diagnostics"]))
        self.assertEqual(result["largest_probability_errors"], [])

    def test_week_one_totals_model_is_saved_without_current_season_diagnostics(self):
        data = read_json(DATA)
        engine = SimpleNamespace(team_by_game={(g["game_id"], g["home_team"]): {} for g in data["schedule"]})
        with TemporaryDirectory() as directory, patch("nfl_predictor.totals.FeatureEngine", return_value=engine), \
                patch("nfl_predictor.totals.CORE", ["offense_sum"]), patch("nfl_predictor.totals.CONTEXT", []), \
                patch("nfl_predictor.totals.total_features", side_effect=lambda _, game: {"offense_sum": game["week"]}):
            output = Path(directory) / "totals"
            result = research_totals(DATA, VENUES, 2026, 1, output)
            self.assertTrue((output / "totals-model.json").is_file())
        self.assertEqual(result["training_cutoff"], {"season": 2026, "before_week": 1})
        expected = sum(2023 <= g["season"] < 2026 and g["home_score"] is not None for g in data["schedule"])
        self.assertEqual(result["training_games"], expected)
        self.assertEqual(result["diagnostic"], {"games": 0, "mae": None, "rmse": None, "mean_error": None})

    def test_empty_tuning_or_later_week_diagnostics_still_fail(self):
        frame = pd.DataFrame({"season": [2025], "week": [1], "target": [1], "total": [40], "x": [1.]})
        with self.assertRaisesRegex(ValueError, "No evaluation games"):
            rolling(frame, 2026, ["x"], 60., through_week=1, allow_empty=True)
        with self.assertRaisesRegex(ValueError, "No rolling total"):
            rolling_totals(frame, 2026, ["x"], 60., through_week=1, allow_empty=True)


if __name__ == "__main__":
    unittest.main()
