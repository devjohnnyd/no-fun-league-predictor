import unittest

from nfl_predictor.engine import FeatureEngine


class BodyClockTests(unittest.TestCase):
    def engine(self, venue_zone="America/New_York", longitude=-76.6):
        data = {"schedule": [], "players": [], "team_games": [], "qb_games": [], "snaps": [], "injuries": [], "ngs": [], "kicks": []}
        venues = {"team_homes": {"LAC": {"latitude": 33.95, "longitude": -118.34, "timezone": "America/Los_Angeles"}},
                  "stadiums": {"X": {"latitude": 39.3, "longitude": longitude, "timezone": venue_zone}}}
        return FeatureEngine(data, venues)

    def game(self, **overrides):
        return {"game_id": "2026_10_LAC_BAL", "season": 2026, "week": 10, "gameday": "2026-11-15", "gametime": "13:00",
                "home_team": "BAL", "away_team": "LAC", "location": "Home", "stadium_id": "X", "home_rest": 7, "away_rest": 7, **overrides}

    def test_west_coast_early_eastern_game_is_ten_am_at_home(self):
        state = self.engine().travel_state("LAC", self.game())
        self.assertEqual(state["clock_shift"], 3)
        self.assertEqual(state["zones_crossed"], 3)
        self.assertEqual(state["eastward"], 3)
        self.assertEqual(state["early_clock"], 2)
        self.assertIn("T10:00", state["home_clock_kickoff"])

    def test_night_game_has_different_home_clock_exposure(self):
        state = self.engine().travel_state("LAC", self.game(gametime="20:15"))
        self.assertEqual(state["early_clock"], 0)
        self.assertIn("T17:15", state["home_clock_kickoff"])

    def test_dst_is_resolved_on_the_game_date(self):
        # Arizona remains UTC-7 while California observes daylight saving time.
        engine = self.engine("America/Phoenix", -112.1)
        self.assertEqual(engine.travel_state("LAC", self.game(gameday="2026-09-20"))["clock_shift"], 0)
        self.assertEqual(engine.travel_state("LAC", self.game(gameday="2026-11-15"))["clock_shift"], 1)

    def test_international_phase_wraps_across_date_line(self):
        state = self.engine("Australia/Melbourne", 144.96).travel_state("LAC", self.game(gameday="2026-09-10"))
        self.assertEqual(state["utc_offset_difference"], 17)
        self.assertEqual(state["clock_shift"], -7)
        self.assertEqual(state["zones_crossed"], 7)

    def test_neutral_site_cannot_fall_back_to_home_stadium(self):
        self.assertIsNone(self.engine().travel_state("LAC", self.game(location="Neutral"))["clock_shift"])

    def test_short_rest_is_separate_from_assumed_arrival_time(self):
        short = self.engine().travel_state("LAC", self.game(away_rest=4))
        long = self.engine().travel_state("LAC", self.game(away_rest=14))
        self.assertGreater(short["rest_adjusted_shift"], long["rest_adjusted_shift"])
