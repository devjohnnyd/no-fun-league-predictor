import copy
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nfl_predictor.dashboard import injury_reports
from nfl_predictor.locks import LockError, PickLocks, check_password, projected_qbs

BEFORE = datetime(2026, 11, 29, 12, tzinfo=timezone.utc)


def game_row(**changes):
    row = {"eventId": "401", "season": 2026, "week": 13, "kickoff": "2026-11-29T18:00:00Z", "state": "pre",
           "homeCode": "PIT", "awayCode": "CLE", "homeScore": None, "awayScore": None,
           "pick": "PIT", "homeProbability": .62, "pickProbability": .62, "predictionStage": "preliminary",
           "forecastIssuedAt": "2026-11-28T15:00:00+00:00", "modelName": "v4_baseline_rebuilt",
           "homeQb": "Aaron Rodgers", "awayQb": "Joe Flacco", "homeQbStatus": "No current designation reported", "awayQbStatus": "No current designation reported",
           "homeInjuries": [{"name": "T.J. Watt", "position": "OLB", "status": "Questionable"}], "awayInjuries": [],
           "weather": {"outdoor": True, "temperature_f": 38.0, "wind_mph": 6.0, "precip_probability": .1},
           "marketSpread": {"latestLine": -3.5, "book": "Book", "observedAt": "2026-11-28T16:00:00+00:00", "quoteStatus": "pregame",
                            "analysis": {"lean": "Home", "home_cover_probability": .55, "away_cover_probability": .45}, "projection": {"projected_home_margin": 4.4}},
           "marketTotal": {"latestLine": 40.5, "book": "Book", "observedAt": "2026-11-28T16:00:00+00:00", "quoteStatus": "pregame",
                           "analysis": {"lean": "Under", "over_probability": .44, "under_probability": .56}, "projection": {"projected_total": 38.9}},
           "forecastSources": {"depth": {"status": "ok", "retrieved_at": "2026-11-28T14:50:00+00:00"}}}
    row.update(changes)
    return row


def payload(*rows):
    return {"period": {"season": 2026, "week": 13}, "queries": {"matchups": {"rows": list(rows)}}}


class LockTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.locks = PickLocks(Path(self.directory.name) / "locks.sqlite3")

    def tearDown(self):
        self.directory.cleanup()

    def test_lock_freezes_the_pregame_view_and_rejects_relocks_and_started_games(self):
        receipt = self.locks.lock(game_row(), {}, BEFORE)
        self.assertEqual(receipt["eventId"], "401")
        with self.assertRaises(LockError):
            self.locks.lock(game_row(), {}, BEFORE)
        with self.assertRaises(LockError):
            self.locks.lock(game_row(eventId="402", state="in"), {}, BEFORE)
        with self.assertRaises(LockError):
            self.locks.lock(game_row(eventId="403"), {}, datetime(2026, 11, 29, 18, tzinfo=timezone.utc))
        with self.assertRaises(LockError):
            self.locks.lock(game_row(eventId="404", pick=None), {}, BEFORE)
        source = payload(game_row())
        enriched = self.locks.enrich(source, {})
        lock = enriched["queries"]["matchups"]["rows"][0]["lock"]
        self.assertNotIn("lock", source["queries"]["matchups"]["rows"][0])
        self.assertEqual(lock["snapshot"]["qbs"]["home"]["name"], "Aaron Rodgers")
        self.assertEqual(lock["snapshot"]["spread"], {"line": -3.5, "book": "Book", "observedAt": "2026-11-28T16:00:00+00:00",
                                                      "quoteStatus": "pregame", "lean": "Home", "probability": .55, "projection": 4.4})
        self.assertEqual(lock["snapshot"]["total"]["lean"], "Under")
        self.assertEqual(lock["changes"], [])
        self.assertIsNone(lock["result"])

    def test_released_quarterback_and_later_news_are_reported_after_the_lock(self):
        self.locks.lock(game_row(), {}, BEFORE)
        # A newer input check projects a different starter, even though no new forecast was released.
        inputs = {"401": {"checkedAt": "2026-11-29T13:00:00+00:00",
                          "qbs": {"home": {"name": "Mason Rudolph", "status": "No current designation reported"},
                                  "away": {"name": "Joe Flacco", "status": "Questionable"}}}}
        later = game_row(homeProbability=.45, pick="CLE",
                         homeInjuries=[{"name": "T.J. Watt", "position": "OLB", "status": "Out"}],
                         weather={"outdoor": True, "temperature_f": 36.0, "wind_mph": 18.0, "precip_probability": .1},
                         marketSpread={**game_row()["marketSpread"], "latestLine": 1.5, "analysis": {"lean": "Away", "home_cover_probability": .4, "away_cover_probability": .6}})
        row = self.locks.enrich(payload(later), inputs)["queries"]["matchups"]["rows"][0]
        self.assertEqual(row["currentQbs"]["home"]["name"], "Mason Rudolph")
        found = {(item["kind"], item["label"]): item for item in row["lock"]["changes"]}
        self.assertEqual(found[("qb", "PIT starting QB changed")]["after"], "Mason Rudolph")
        self.assertEqual(found[("qb", "PIT starting QB changed")]["severity"], "major")
        self.assertEqual(found[("qb", "CLE QB status changed")]["severity"], "minor")
        self.assertEqual(found[("pick", "Model now picks the other team")]["after"], "CLE")
        self.assertEqual((found[("probability", "PIT win probability")]["before"], found[("probability", "PIT win probability")]["after"]), ("62%", "45%"))
        self.assertEqual(found[("spread", "Spread line moved")]["after"], 1.5)
        self.assertEqual(found[("spread", "Spread lean flipped")]["severity"], "major")
        self.assertEqual(found[("injury", "PIT T.J. Watt")]["severity"], "major")
        self.assertEqual(found[("weather", "Wind")]["after"], "18 mph")
        self.assertNotIn(("total", "Total line moved"), found)
        self.assertNotIn(("weather", "Temperature"), found)

    def test_result_grades_the_bet_as_locked_and_notes_the_latest_pick(self):
        self.locks.lock(game_row(), {}, BEFORE)
        final = game_row(state="post", homeScore=17, awayScore=20, pick="CLE", homeProbability=.48)
        result = self.locks.enrich(payload(final), {})["queries"]["matchups"]["rows"][0]["lock"]["result"]
        self.assertEqual(result, {"winner": "Lost", "spread": "Lost", "total": "Won", "latestPick": {"pick": "CLE", "outcome": "Won"}})
        push = game_row(state="post", homeScore=20, awayScore=20)
        self.assertEqual(self.locks.enrich(payload(push), {})["queries"]["matchups"]["rows"][0]["lock"]["result"]["winner"], "Tie")

    def test_only_a_newer_input_check_overrides_the_forecast_quarterbacks(self):
        stale = {"401": {"checkedAt": "2026-11-28T10:00:00+00:00", "qbs": {"home": {"name": "Old"}, "away": {"name": "Old"}}}}
        self.assertEqual(projected_qbs(game_row(), stale)["source"], "Saved forecast")
        self.assertEqual(projected_qbs(game_row(forecastIssuedAt="2026-11-27"), {"401": {**stale["401"], "checkedAt": "2026-11-28T10:00:00+00:00"}})["source"], "Latest input check")

    def test_password_comes_only_from_the_environment(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(LockError) as missing:
                check_password("anything")
            self.assertEqual(missing.exception.status, 503)
        with patch.dict(os.environ, {"NFL_LOCK_PASSWORD": "secret"}), patch("nfl_predictor.locks.time.sleep") as delay:
            check_password("secret")
            with self.assertRaises(LockError) as wrong:
                check_password("guess")
            self.assertEqual(wrong.exception.status, 403)
            delay.assert_called_once()
            with self.assertRaises(LockError):
                check_password(None)

    def test_dashboard_keeps_designated_players_from_the_forecast(self):
        prediction = {"detail": {"home_injuries": {"reports": [{"name": "A", "position": "WR", "status": "Out", "pid": "1"}, {"name": "B", "status": None}]}}}
        self.assertEqual(injury_reports(prediction, "home"), [{"name": "A", "position": "WR", "status": "Out"}])
        self.assertEqual(injury_reports(prediction, "away"), [])
        self.assertEqual(injury_reports(None, "home"), [])


if __name__ == "__main__":
    unittest.main()
