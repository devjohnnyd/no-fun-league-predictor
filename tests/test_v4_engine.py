import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from nfl_predictor.engine import FeatureEngine, weighted_rate
from nfl_predictor.live import collect_staff, coverage, parse_staff, require_known_qbs
from nfl_predictor.research import feature_frame, paired_brier, reliability
from nfl_predictor.storage import clean, read_json

ROOT = Path(__file__).resolve().parents[1]


class V4EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = read_json(ROOT / "data/snapshots/dataset-v4-2026-11-16.json.gz")
        cls.venues = read_json(ROOT / "data/snapshots/venues-v4-2026-11-15.json")

    def test_all_completed_games_reconcile_and_sources_have_hashes(self):
        self.assertEqual(self.data["quality"]["completed_games_missing_pbp"], [])
        self.assertEqual(self.data["quality"]["seasons"]["2026"]["pbp_games"], 149)
        self.assertTrue(all(len(source["sha256"]) == 64 for source in self.data["sources"]))

    def test_impossible_pressure_percentage_is_excluded(self):
        invalid = self.data["quality"]["invalid_pressure_rows_excluded"]
        self.assertEqual(len(invalid), 1)
        row = next(r for r in self.data["qb_games"] if r["game_id"] == invalid[0]["game_id"] and r["pid"] == invalid[0]["pid"])
        self.assertIsNone(row["pressure_n"])
        self.assertEqual(row["pfr_db"], 0)

    def test_season_summary_rows_cannot_enter_weekly_tracking_features(self):
        self.assertGreater(self.data["quality"]["ngs_week_zero_excluded"], 0)
        self.assertTrue(all(row["week"] > 0 for row in self.data["ngs"]))

    def test_target_and_future_statistics_cannot_change_features(self):
        game = next(g for g in self.data["schedule"] if g["season"] == 2026 and g["week"] == 9)
        expected = clean(FeatureEngine(self.data, self.venues).features(game)[0])
        changed = copy.deepcopy(self.data)
        for row in changed["team_games"]:
            if (row["season"], row["week"]) >= (2026, 9):
                for name in ("epa", "pass_epa", "def_epa", "def_pass_epa", "special_epa"):
                    row[name] += 10000
        for row in changed["qb_games"]:
            if (row["season"], row["week"]) >= (2026, 9):
                row["epa"] += 10000
                row["int_worthy"] += 1000
        for row in changed["ngs"]:
            if (row["season"], row["week"]) >= (2026, 9):
                for key in ("avg_time_to_throw", "avg_separation", "rush_yards_over_expected"):
                    if key in row:
                        row[key] = 9999
        actual = clean(FeatureEngine(changed, self.venues).features(game)[0])
        self.assertEqual(expected, actual)

    def test_coverage_requires_the_whole_previous_week(self):
        engine = FeatureEngine(self.data, self.venues)
        self.assertTrue(coverage(engine, 2026, 10)["complete"])
        self.assertEqual(coverage(engine, 2026, 10)["expected_games"], 136)
        self.assertFalse(coverage(engine, 2026, 11)["complete"])

    def test_rate_uses_exposure_not_an_average_of_averages(self):
        rows = [({"value": 10, "n": 10}, 1), ({"value": 0, "n": 90}, 1)]
        self.assertAlmostEqual(weighted_rate(rows, "value", "n", strength=0), .1)
        self.assertIsNone(weighted_rate([], "value", "n", unknown=True))

    def test_official_branding_and_home_city_coverage(self):
        self.assertEqual(len(self.venues["team_homes"]), 32)
        self.assertEqual(self.venues["errors"], [])
        for team in self.venues["teams"].values():
            self.assertIn("static.www.nfl.com/", team["logo_url"])
            self.assertTrue((ROOT / "assets/team-logos" / team["logo_file"]).is_file())

    def test_staff_role_adjacency_does_not_accept_names_in_unrelated_text(self):
        seed = {"head_coach": "Old Coach"}
        parsed = parse_staff("<p>Old Coach left</p><h3>New Person</h3><h4>Head Coach</h4>", seed)
        self.assertEqual(parsed["head_coach"], "New Person")
        self.assertIsNone(parsed["offensive_coordinator"])
        parsed = parse_staff("<h3>Jesse Minter</h3><h4>Head Coach</h4><p>JESSE MINTER</p>", {"head_coach": "Jesse Minter"})
        self.assertEqual(parsed["head_coach"], "Jesse Minter")

    def test_staff_accepts_interim_roles_and_releases_without_a_coordinator(self):
        parsed = parse_staff("<h3>Todd Wash</h3><h4>Interim defensive coordinator</h4>", {})
        self.assertEqual(parsed["defensive_coordinator"], "Todd Wash")
        page = b"<h3>Head Person</h3><h4>Head Coach</h4><h3>Off Person</h3><h4>Offensive Coordinator</h4>"
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = page
        with tempfile.TemporaryDirectory() as folder, mock.patch("nfl_predictor.live.urlopen", return_value=response):
            staff, receipt = collect_staff({"source": "https://example.test/staff"}, Path(folder) / "staff.html")
        self.assertIsNone(staff["defensive_coordinator"])
        self.assertEqual(receipt["status"], "ok")
        response.__enter__.return_value.read.return_value = b"<h3>Off Person</h3><h4>Offensive Coordinator</h4>"
        with tempfile.TemporaryDirectory() as folder, mock.patch("nfl_predictor.live.urlopen", return_value=response):
            _, receipt = collect_staff({"source": "https://example.test/staff"}, Path(folder) / "staff.html")
        self.assertEqual(receipt["status"], "unverified")

    def test_unmapped_projected_qb_blocks_unless_a_debut_is_confirmed(self):
        players = {"00-1": {}}
        require_known_qbs(players, {"KC": {"qb_id": "00-1", "qb_name": "Known"}})
        with self.assertRaisesRegex(ValueError, "no statistics identity"):
            require_known_qbs(players, {"KC": {"qb_id": "ESPN:99", "qb_name": "Unknown"}})
        require_known_qbs(players, {"KC": {"qb_id": "ESPN:99", "qb_name": "Rookie", "qb_debut_confirmed": True}})

    def test_reliability_shows_sampling_uncertainty(self):
        bins = reliability([1, 0], [.7, .7])
        row = next(r for r in bins if r["games"])
        self.assertEqual(row["observed_accuracy"], .5)
        self.assertLess(row["accuracy_wilson_95"][0], .5)
        self.assertGreater(row["accuracy_wilson_95"][1], .5)

    def test_week_bootstrap_is_paired_by_game_and_reproducible(self):
        import pandas as pd
        base = pd.DataFrame({"game_id": ["a", "b"], "week": [1, 2], "target": [1, 0], "p": [.5, .5]})
        better = base.copy()
        better["p"] = [.8, .2]
        first, second = paired_brier(better, base), paired_brier(better, base)
        self.assertEqual(first, second)
        self.assertAlmostEqual(first["delta_brier"], -.21)
