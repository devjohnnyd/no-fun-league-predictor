import unittest

from nfl_predictor.sources import depth_quarterbacks, unique_venue_city


class SourceCoverageTests(unittest.TestCase):
    def test_geocoding_does_not_pick_first_ambiguous_city(self):
        venue = {"address": {"city": "Baltimore", "state": "MD", "country": "USA"}}
        ohio = {"name": "Baltimore", "country_code": "US", "admin1": "Ohio"}
        maryland = {**ohio, "admin1": "Maryland"}
        self.assertEqual(unique_venue_city(venue, {"results": [ohio, maryland]}), maryland)
        with self.assertRaises(ValueError):
            unique_venue_city(venue, {"results": [maryland, maryland]})
        with self.assertRaises(ValueError):
            unique_venue_city(venue, {"results": [ohio]})

    def test_missing_us_state_cannot_disambiguate_a_city(self):
        with self.assertRaises(ValueError):
            unique_venue_city({"address": {"city": "Baltimore", "country": "USA"}}, {"results": []})

    def test_empty_or_wrong_team_depth_is_missing_not_healthy(self):
        with self.assertRaises(ValueError):
            depth_quarterbacks({"team": {"id": "1"}, "depthchart": []}, "1")
        with self.assertRaises(ValueError):
            depth_quarterbacks({"team": {"id": "2"}}, "1")

    def test_depth_qb_candidates_are_preserved(self):
        payload = {"team": {"id": "1"}, "depthchart": [{"positions": {"qb": {"athletes": [
            {"id": "10", "displayName": "Test QB", "injuries": [{"status": "Questionable"}]}]}}}]}
        self.assertEqual(depth_quarterbacks(payload, "1")[0]["injuries"][0]["status"], "Questionable")
