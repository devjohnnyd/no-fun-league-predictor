import copy
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from nfl_predictor.engine import FeatureEngine
from nfl_predictor.storage import read_json
from nfl_predictor.totals import card_rows, fit_total, line_analysis, predict_total, saved_total_pick, score_card, total_features

ROOT = Path(__file__).resolve().parents[1]


class TotalsTests(unittest.TestCase):
    def test_half_point_lines_have_no_push_and_probabilities_sum_to_one(self):
        result = line_analysis({"total_samples": [40, 42, 43, 50]}, 42.5)
        self.assertEqual(result["push_probability"], 0)
        self.assertAlmostEqual(result["over_probability"] + result["under_probability"], 1)

    def test_whole_point_push_is_separate(self):
        result = line_analysis({"total_samples": [40, 42, 42, 50]}, 42)
        self.assertGreater(result["push_probability"], 0)
        self.assertAlmostEqual(sum(result[key] for key in ("over_probability", "under_probability", "push_probability")), 1)

    def test_invalid_lines_fail(self):
        for line in (float("nan"), -1, 42.25, 200):
            with self.assertRaises(ValueError):
                line_analysis({"total_samples": [40, 50]}, line)

    def test_brochure_photo_lines_and_actual_results_are_not_backfilled_picks(self):
        card = read_json(ROOT / "data/cards/2026-week10.json")
        games = read_json(ROOT / "data/snapshots/week10-results-2026-11-16-morning.json")["games"]
        rows = card_rows(card, games, {})
        self.assertEqual([row["line"] for row in rows], [42.5, 43.5, 47.5])
        self.assertEqual([row["actualTotal"] for row in rows], [40, 34, 56])
        self.assertEqual([row["actualOutcome"] for row in rows], ["Under", "Under", "Over"])
        self.assertTrue(all(row["correct"] is None and row["analysis"] is None for row in rows))

    def test_card_requires_three_distinct_matching_games(self):
        card = read_json(ROOT / "data/cards/2026-week10.json")
        card["games"][1] = card["games"][0]
        with self.assertRaises(ValueError):
            card_rows(card, [], {})

    def test_historical_brochure_is_not_scored_as_three_losses(self):
        result = score_card(read_json(ROOT / "data/cards/2026-week10.json"), [], read_json(ROOT / "data/snapshots/week10-results-2026-11-16-morning.json"))
        self.assertEqual(result["metrics"]["games"], 0)
        self.assertEqual(result["unavailable_predictions"], 3)

    def test_reported_over_choices_have_a_separate_one_and_two_record(self):
        result = score_card(read_json(ROOT / "data/cards/2026-week10.json"), [], read_json(ROOT / "data/snapshots/week10-results-2026-11-16-morning.json"))
        self.assertEqual(result["user_record"]["wins"], 1)
        self.assertEqual(result["user_record"]["losses"], 2)
        self.assertEqual(result["user_record"]["reported_after_kickoff"], 3)
        self.assertEqual(result["metrics"]["games"], 0)
        self.assertEqual(len({row["selectionId"] for row in result["games"]}), 3)

    def test_live_totals_are_not_settled_and_missing_scores_stay_unknown(self):
        card = read_json(ROOT / "data/cards/2026-week10.json")
        games = read_json(ROOT / "data/snapshots/week10-results-2026-11-16-morning.json")["games"]
        for game in games:
            game.update(completed=False, state="in", home_live_score=30, away_live_score=20)
        rows = card_rows(card, games, {})
        self.assertTrue(all(row["liveTotal"] == 50 and row["actualOutcome"] is None and row["userCorrect"] is None for row in rows))
        for game in games:
            game["home_live_score"] = None
        self.assertTrue(all(row["liveTotal"] is None for row in card_rows(card, games, {})))

    def test_invalid_user_pick_is_rejected(self):
        card = read_json(ROOT / "data/cards/2026-week10.json")
        card["games"][0]["user_pick"]["pick"] = "Maybe"
        with self.assertRaisesRegex(ValueError, "User total pick"):
            card_rows(card, read_json(ROOT / "data/snapshots/week10-results-2026-11-16-morning.json")["games"], {})

    def test_original_total_pick_survives_newer_winner_and_totals_revisions(self):
        card = read_json(ROOT / "data/cards/2026-week10.json")
        card["received_at"] = "2026-11-13T12:00:00Z"
        results = read_json(ROOT / "data/snapshots/week10-results-2026-11-16-morning.json")
        original = {"issued_at": "2026-11-13T13:00:00Z", "forecast": [
            {"espn_id": row["event_id"], "home": row["home"], "away": row["away"],
             "total_projection": {"total_samples": [30, 31, 32]}} for row in card["games"]]}
        revised = copy.deepcopy(original)
        revised["issued_at"] = "2026-11-13T14:00:00Z"
        for row in revised["forecast"]:
            row["total_projection"]["total_samples"] = [60, 61, 62]
        winner_only = copy.deepcopy(revised)
        winner_only["issued_at"] = "2026-11-13T15:00:00Z"
        for row in winner_only["forecast"]:
            del row["total_projection"]
        result = score_card(card, [winner_only, revised, original], results)
        self.assertTrue(all(row["analysis"]["lean"] == "Under" for row in result["games"]))
        self.assertTrue(all(row["forecastIssuedAt"] == original["issued_at"] for row in result["games"]))

    def test_frozen_total_choice_rejects_late_release_or_changed_line(self):
        card = read_json(ROOT / "data/cards/2026-week10.json")
        card["received_at"] = "2026-11-13T12:00:00Z"
        game = read_json(ROOT / "data/snapshots/week10-results-2026-11-16-morning.json")["games"][0]
        selection = card["games"][0]
        games = read_json(ROOT / "data/snapshots/week10-results-2026-11-16-morning.json")["games"]
        game = next(g for g in games if g["event_id"] == selection["event_id"])
        forecast = {"home": selection["home"], "away": selection["away"], "kickoff": game["kickoff"],
                    "issued_at": "2026-11-13T13:00:00Z", "total_projection": {"total_samples": [30, 35, 50]}}
        forecast["total_pick"] = saved_total_pick(card, selection, forecast, forecast["issued_at"])
        with self.assertRaises(ValueError):
            saved_total_pick(card, selection, forecast, game["kickoff"])
        with self.assertRaises(ValueError):
            saved_total_pick(card, selection, forecast, "2026-11-13T11:00:00Z")
        forecasts = {selection["event_id"]: forecast}
        self.assertIsNotNone(card_rows(card, games, forecasts)[0]["analysis"])
        card["games"][0]["line"] += 1
        with self.assertRaisesRegex(ValueError, "Saved total pick differs"):
            card_rows(card, games, forecasts)

    def test_pregame_card_uses_saved_distribution_and_separates_a_push(self):
        card = read_json(ROOT / "data/cards/2026-week10.json")
        card["received_at"] = "2026-11-13T12:00:00Z"
        card["games"][0]["line"] = 40.
        results = read_json(ROOT / "data/snapshots/week10-results-2026-11-16-morning.json")
        batch = {"issued_at": "2026-11-13T13:00:00Z", "forecast": [
            {"espn_id": row["event_id"], "home": row["home"], "away": row["away"], "total_projection": {"total_samples": [30, 35, 40, 45, 50]}} for row in card["games"]]}
        result = score_card(card, [batch], results)
        self.assertEqual(result["metrics"]["games"], 2)
        self.assertEqual(result["pushes"], 1)

    def test_late_brochure_line_cannot_become_a_pregame_lean(self):
        card = read_json(ROOT / "data/cards/2026-week10.json")
        card["received_at"] = "2026-11-16T14:00:00Z"
        games = read_json(ROOT / "data/snapshots/week10-results-2026-11-16-morning.json")["games"]
        forecasts = {row["event_id"]: {"home": row["home"], "away": row["away"], "total_projection": {"total_samples": [30,40,50]}} for row in card["games"]}
        self.assertTrue(all(row["analysis"] is None for row in card_rows(card, games, forecasts)))

    def test_even_leans_are_abstentions_in_rows_and_summary(self):
        card = read_json(ROOT / "data/cards/2026-week10.json")
        card["received_at"] = "2026-11-13T12:00:00Z"
        results = read_json(ROOT / "data/snapshots/week10-results-2026-11-16-morning.json")
        batch = {"issued_at": "2026-11-13T13:00:00Z", "forecast": [
            {"espn_id": row["event_id"], "home": row["home"], "away": row["away"],
             "total_projection": {"total_samples": [30, 60]}} for row in card["games"]]}
        result = score_card(card, [batch], results)
        self.assertEqual(result["abstentions"], 3)
        self.assertEqual(result["metrics"]["games"], 0)
        self.assertIsNone(result["metrics"]["accuracy"])
        self.assertTrue(all(row["correct"] is None for row in result["games"]))
        self.assertTrue(all(row["predictionStatus"] == "No directional lean (50/50)" for row in result["games"]))

    def test_directional_pick_summary_agrees_with_each_card(self):
        card = read_json(ROOT / "data/cards/2026-week10.json")
        card["received_at"] = "2026-11-13T12:00:00Z"
        results = read_json(ROOT / "data/snapshots/week10-results-2026-11-16-morning.json")
        batch = {"issued_at": "2026-11-13T13:00:00Z", "forecast": [
            {"espn_id": row["event_id"], "home": row["home"], "away": row["away"],
             "total_projection": {"total_samples": [30, 35, 60]}} for row in card["games"]]}
        result = score_card(card, [batch], results)
        self.assertEqual(result["abstentions"], 0)
        self.assertEqual(result["metrics"]["games"], 3)
        self.assertEqual(result["metrics"]["correct"], sum(row["correct"] for row in result["games"]))

    def test_regression_accepts_tied_nfl_games_and_keeps_preprocessing_fixed(self):
        train = pd.DataFrame({"x": [1., 2., 3., 4.], "total": [40, 42, 38, 44]})
        model = fit_total(train, ["x"], 60.)
        means = copy.deepcopy(model["mean"])
        values = predict_total(model, pd.DataFrame({"x": [1000., np.nan]}))
        self.assertTrue(np.isfinite(values).all())
        self.assertEqual(model["mean"], means)

    def test_target_score_and_future_stats_cannot_change_total_features(self):
        data = read_json(ROOT / "data/snapshots/dataset-v4-2026-11-16.json.gz")
        venues = read_json(ROOT / "data/snapshots/venues-v4-2026-11-15.json")
        game = next(g for g in data["schedule"] if g["season"] == 2026 and g["week"] == 9)
        expected = total_features(FeatureEngine(data, venues), game)
        altered = copy.deepcopy(data)
        for row in altered["team_games"]:
            if (row["season"], row["week"]) >= (2026, 9):
                row["plays"] += 100000
                row["epa"] += 100000
        changed_game = {**game, "home_score": 1000, "away_score": 1000}
        self.assertEqual(expected, total_features(FeatureEngine(altered, venues), changed_game))
