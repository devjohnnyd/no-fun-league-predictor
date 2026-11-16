"""Integration checks against the frozen pregame data, with no network calls."""

import json
from pathlib import Path
import unittest

import numpy as np

from nfl_predictor.evaluate import rolling
from nfl_predictor.features import BASE_NAMES, load_features

ROOT = Path(__file__).resolve().parents[1]


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = load_features(ROOT)

    def test_frozen_batch_and_training_grain(self):
        self.assertFalse(self.frame.game_id.duplicated().any())
        self.assertEqual(int(self.frame.target.isin([0, 1]).sum()), 950)
        self.assertEqual(int(self.frame.live.sum()), 13)
        self.assertEqual(int((self.frame.target.eq(.5)).sum()), 2)
        self.assertEqual(int(self.frame[self.frame.season.eq(2026)].target.isin([0, 1]).sum()), 135)

    def test_frozen_v2_probabilities_are_reproduced(self):
        result = rolling(self.frame, 2026, BASE_NAMES, 60.)
        old = json.loads((ROOT / "archive/session-2026-11-10/enhanced/model.json").read_text())
        old_by_game = {g["game_id"]: g["p"] for g in old["backtest"]}
        self.assertEqual(len(result), len(old_by_game))
        self.assertLess(max(abs(r.home_probability - old_by_game[r.game_id])
                            for r in result.itertuples()), 1e-7)
        self.assertTrue(all((r.train_last_season, r.train_last_week) < (r.season, r.week)
                            for r in result.itertuples()))

    def test_live_qb_is_original_projection(self):
        row = self.frame[self.frame.game_id.eq("2026_10_LAC_BAL")].iloc[0]
        old = json.loads((ROOT / "archive/session-2026-11-10/enhanced/model.json").read_text())
        forecast = next(g for g in old["forecast"] if g["game_id"] == row.game_id)
        self.assertEqual(row.home_qb_id, forecast["home_qb"]["id"])
        self.assertTrue(np.isfinite(row.qb_coach_familiarity_diff))
