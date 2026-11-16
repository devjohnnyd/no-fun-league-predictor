import copy
import unittest

import numpy as np

from nfl_predictor.features import History


def game(week, qb="qb1", coach="coach", season=2026):
    return {"game_id": f"{season}_{week:02d}_A_H", "season": season, "week": week,
            "home_team": "H", "away_team": "A", "home_qb_id": qb,
            "away_qb_id": "other", "home_coach": coach, "away_coach": "othercoach",
            "home_score": 21, "away_score": 14}


class TemporalFeatureTests(unittest.TestCase):
    def setUp(self):
        self.games = [game(1), game(2), game(3, qb="newqb")]
        self.teams = {g["game_id"] + "|" + team: {"hits": 3, "db": 30, "def_hits": 6, "def_db": 30}
                      for g in self.games for team in ("H", "A")}
        self.lineups = {self.games[0]["game_id"] + "|H": ["a", "b", "c", "d", "e"],
                        self.games[1]["game_id"] + "|H": ["a", "b", "c", "d", "f"]}
        self.qbs = {"qb1": [{"game_id": g["game_id"], "season": 2026, "week": g["week"], "db": 30, "team": "H"}
                             for g in self.games]}

    def history(self):
        return History(self.games, self.teams, self.qbs, self.lineups)

    def test_target_game_and_future_stats_do_not_enter_features(self):
        before = self.history().protection("H", 2026, 2)
        self.teams[self.games[1]["game_id"] + "|H"]["hits"] = 999
        self.teams[self.games[2]["game_id"] + "|H"]["hits"] = 999
        self.assertEqual(before, self.history().protection("H", 2026, 2))
        self.assertAlmostEqual(before[0], (3 + 15) / 130)

    def test_lineup_continuity_uses_two_prior_team_games(self):
        self.assertAlmostEqual(self.history().continuity("H", 2026, 3), .8)
        self.lineups[self.games[2]["game_id"] + "|H"] = ["z"] * 5
        self.assertAlmostEqual(self.history().continuity("H", 2026, 3), .8)

    def test_missing_lineup_and_offseason_are_unknown(self):
        self.assertTrue(np.isnan(self.history().continuity("H", 2026, 2)))
        self.assertTrue(np.isnan(self.history().continuity("H", 2027, 1)))

    def test_qb_transition_and_familiarity_are_lagged(self):
        change, familiarity = self.history().transition("H", "qb1", "coach", 2026, 2)
        self.assertEqual(change, 0)
        self.assertAlmostEqual(familiarity, np.log1p(30))
        self.assertEqual(self.history().transition("H", "newqb", "coach", 2026, 3)[0], 1)

    def test_backups_use_their_team_not_recorded_starter(self):
        self.qbs["backup"] = copy.deepcopy(self.qbs["qb1"])
        self.assertAlmostEqual(self.history().transition("H", "backup", "coach", 2026, 2)[1], np.log1p(30))

    def test_coach_familiarity_survives_team_change(self):
        # Coach and QB move together; the same head coach still counts.
        self.assertAlmostEqual(self.history().transition("NEW", "qb1", "coach", 2026, 2)[1], np.log1p(30))
        self.assertEqual(self.history().transition("H", "qb1", "different", 2026, 2)[1], 0)
