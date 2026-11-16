import unittest

from nfl_predictor.market import aligned_consensus, espn_quotes, implied_probability, remove_margin


class MarketTests(unittest.TestCase):
    def test_margin_is_removed_from_a_paired_book(self):
        result = remove_margin(-110, -110)
        self.assertEqual(result["home_probability"], .5)
        self.assertGreater(result["overround"], 0)
        self.assertAlmostEqual(implied_probability(200), 1 / 3)

    def test_invalid_prices_are_not_silently_used(self):
        for value in (0, 50, float("nan")):
            with self.assertRaises(ValueError):
                implied_probability(value)

    def test_quotes_after_issue_and_after_kickoff_are_excluded(self):
        quote = {"event_id": "1", "book": "test", "observed_at": "2026-11-16T20:00:00Z", "home_price": -110, "away_price": -110}
        self.assertEqual(aligned_consensus([quote], "2026-11-16T19:59:00Z", "2026-11-17T01:15:00Z")["status"], "unavailable")
        self.assertEqual(aligned_consensus([quote], "2026-11-16T20:11:00Z", "2026-11-17T01:15:00Z")["status"], "unavailable")
        self.assertEqual(aligned_consensus([quote], "2026-11-16T20:05:00Z", "2026-11-17T01:15:00Z")["status"], "ok")

    def test_espn_close_field_is_only_accepted_when_observed_pregame(self):
        summary = {"pickcenter": [{"moneyline": {"home": {"close": {"odds": "-225"}}, "away": {"close": {"odds": "+185"}}}}]}
        game = {"event_id": "1", "kickoff": "2026-11-17T01:15:00Z"}
        self.assertEqual(len(espn_quotes(summary, game, {"retrieved_at": "2026-11-17T01:14:00Z", "url": "https://example.org"})), 1)
        self.assertEqual(espn_quotes(summary, game, {"retrieved_at": "2026-11-17T01:16:00Z", "url": "https://example.org"}), [])
