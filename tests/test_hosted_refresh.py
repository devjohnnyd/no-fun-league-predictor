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
