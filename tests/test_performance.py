import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import Mock, patch

from nfl_predictor.line_tracking import LineTracker
from nfl_predictor.performance import SeasonPerformance, season_payload
from nfl_predictor.totals import saved_total_pick


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        teams = [("BAL","LAC"),("BUF","NYJ"),("GB","MIN"),("LV","SEA"),("DET","NE")]
        self.dataset = {"schedule":[{"season":2026,"week":1,"espn":str(i),"game_id":f"2026_01_{away}_{home}",
                       "gameday":"2026-09-10","gametime":"20:20","home_team":home,"away_team":away}
                      for i,(home,away) in enumerate(teams,1)]}
        games = [{"event_id":str(i),"home":home,"away":away,"kickoff":"2026-09-11T00:20:00Z","completed":i<=3,
                  "state":"post" if i<=3 else "pre" if i==4 else "unknown",
                  "home_score":21 if i in (1,3) else 14 if i==2 else None,"away_score":14 if i==1 else 21 if i in (2,3) else None}
                 for i,(home,away) in enumerate(teams,1)]
        self.results = {1:{"season":2026,"week":1,"retrieved_at":"2026-09-12T00:00:00Z","games":games,
                           "scoreboard_source":{"url":"https://example.test/scores","sha256":"receipt","retrieved_at":"2026-09-12T00:00:00Z"}}}
        self.batch = {"as_of":"2026-09-01","forecast":[{"espn_id":str(i),"home":home,"away":away,"pick":home,
                       "home_probability":.8,"game_id":f"2026_01_{away}_{home}"} for i,(home,away) in enumerate(teams,1)]}

    def payload(self,batches=None,observations=(),cards=(),results=None):
        return season_payload(self.dataset,2026,[self.batch] if batches is None else batches,observations,cards,self.results if results is None else results)

    def rows(self,payload,query="performance-picks"):
        return payload["queries"][query]["rows"]

    def metric(self,payload,kind):
        return next(r for r in self.rows(payload,"performance-summary") if r["kind"]==kind)

    def observations(self):
        output = []
        for game,line,analysis in zip(self.results[1]["games"],[42,35,43,42.5,42.5],[
            {"over_probability":.7,"under_probability":.2,"push_probability":.1,"lean":"Over"},
            {"over_probability":.6,"under_probability":.3,"push_probability":.1,"lean":"Over"},
            {"over_probability":.5,"under_probability":.5,"push_probability":0.,"lean":"Even"},
            {"over_probability":.6,"under_probability":.4,"push_probability":0.,"lean":"Over"},None]):
            output.append({"season":2026,"week":1,"event":game["event_id"],"home":game["home"],"away":game["away"],
                           "book":"Book A","book_id":"A","line":line,"observed_at":"2026-09-02T12:00:00Z",
                           "forecast_issued_at":"2026-09-02T11:00:00Z" if analysis else None,
                           "analysis":json.dumps({**analysis,"line":line}) if analysis else None,"url":"https://example.test/odds","source_sha256":"quote"})
        return output

    def test_originals_are_counted_once_and_later_revisions_do_not_rewrite_metrics(self):
        revised = copy.deepcopy(self.batch)
        revised["issued_at"] = "2026-09-02T12:00:00Z"
        for row in revised["forecast"]:
            row.update(pick=row["away"],home_probability=.1)
        data = self.payload([revised,self.batch,self.batch])
        self.assertEqual(len(self.rows(data)),5)
        result = self.metric(data,"winner")
        self.assertEqual((result["recorded"],result["decided"],result["wins"],result["losses"]),(5,2,1,1))
        self.assertEqual((result["pending"],result["ties"],result["unavailable"]),(1,1,1))
        self.assertAlmostEqual(result["brier"],.34)
        self.assertEqual(self.rows(data)[0]["issuePrecision"],"date")
        self.assertEqual(self.rows(data)[0]["revisionCount"],1)
        self.assertEqual(self.rows(data)[0]["latestPick"],"LAC")

    def test_date_only_batches_are_bounded_at_the_end_of_the_eastern_day(self):
        from nfl_predictor.performance import issue_time
        self.assertEqual(issue_time({"as_of":"2026-11-10"})[1],datetime(2026,11,11,4,59,59,999999,tzinfo=timezone.utc))

    def test_market_scores_condition_on_no_push_and_separate_other_outcomes(self):
        result = self.metric(self.payload(observations=self.observations()),"market")
        self.assertEqual((result["recorded"],result["decided"],result["losses"]),(3,1,1))
        self.assertEqual((result["pushes"],result["abstained"],result["pending"],result["noPick"]),(1,1,1,1))
        self.assertAlmostEqual(result["brier"],(.7/.9)**2)
        self.assertEqual(result["probabilityGames"],1)

    def test_reported_user_card_choices_do_not_become_model_predictions(self):
        games = self.results[1]["games"][:3]
        card = {"season":2026,"week":1,"received_at":None,"source":"Supplied printed card","games":[
            {"event_id":game["event_id"],"home":game["home"],"away":game["away"],"line":line,
             "user_pick":{"pick":"Over","reported_at":"2026-09-12T00:00:00Z","source":"User reported later"}}
            for game,line in zip(games,[42.5,30.5,42])]}
        data = self.payload(cards=[card])
        self.assertEqual(self.metric(data,"printed-model")["recorded"],0)
        user = self.metric(data,"printed-user")
        self.assertEqual((user["wins"],user["losses"],user["pushes"],user["reportedLate"]),(1,1,1,3))
        self.assertIsNone(user["brier"])
        self.assertIsNone(user["logLoss"])

    def test_empty_weeks_and_no_results_are_unknown_instead_of_losses_or_zero_accuracy(self):
        data = self.payload(results={})
        winner = self.metric(data,"winner")
        self.assertEqual(winner["unavailable"],5)
        self.assertEqual(winner["losses"],0)
        self.assertIsNone(winner["accuracy"])
        empty = next(r for r in self.rows(data,"performance-weeks") if r["kind"]=="winner" and r["week"]==2)
        self.assertIsNone(empty["accuracyPct"])
        self.assertEqual(empty["recorded"],0)

    def test_late_bad_or_ambiguous_saved_forecasts_fail_closed(self):
        for changes in ({"issued_at":"2026-09-11T00:20:00Z"},{"as_of":"2026-09-11"}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.payload([{**self.batch,**changes}])
        changed = copy.deepcopy(self.batch)
        changed["forecast"][0].update(pick="LAC",home_probability=.1)
        with self.assertRaises(ValueError):
            self.payload([self.batch,changed])
        for value in (float("nan"),True,-.1,1.1):
            changed = copy.deepcopy(self.batch)
            changed["forecast"][0]["home_probability"] = value
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.payload([changed])

    def test_line_changes_or_after_kickoff_quotes_cannot_be_scored_as_original_picks(self):
        observations = self.observations()
        observations[0]["line"] = 40
        with self.assertRaises(ValueError):
            self.payload(observations=observations)
        observations = self.observations()
        observations[0]["observed_at"] = "2026-09-11T00:20:00Z"
        with self.assertRaises(ValueError):
            self.payload(observations=observations)

    def test_streaming_reader_keeps_first_directional_selection_and_missing_pick(self):
        with TemporaryDirectory() as folder:
            tracker = LineTracker(Path(folder)/"lines.db")
            observations = self.observations()
            earlier = {**observations[0],"observed_at":"2026-09-02T10:00:00Z","analysis":None,"forecast_issued_at":None}
            later = {**observations[0],"observed_at":"2026-09-02T14:00:00Z","line":50.5}
            tracker.import_rows([earlier,*observations,later])
            selected = tracker.original_selections(2026)
            self.assertEqual(len(selected),5)
            self.assertEqual(selected[0]["observed_at"],observations[0]["observed_at"])
            self.assertIsNone(selected[-1]["analysis"])

    def test_read_only_feed_caches_results_and_never_enriches_quotes_or_trains(self):
        with TemporaryDirectory() as folder:
            tracker = LineTracker(Path(folder)/"lines.db")
            tracker.import_rows(self.observations())
            before = tracker.export_rows()
            manager = SimpleNamespace(dataset=self.dataset,season=2026,batches=[self.batch],batch_sources=[],lock=threading.RLock(),
                                      line_tracker=tracker,card_path=Path(folder)/"2026-week1.json",feed=Mock())
            feed = SeasonPerformance(manager,ttl=0)
            manifest = {**self.results[1],"retrieved_at":datetime.now(timezone.utc).isoformat()}
            with patch("nfl_predictor.server.fetch_week",return_value=manifest) as fetch:
                feed.get()
                feed.get()
            self.assertEqual(fetch.call_count,1)
            manager.feed.assert_not_called()
            self.assertEqual(tracker.export_rows(),before)

    def test_result_failure_retains_prior_receipt_and_missing_initial_result_is_unavailable(self):
        with TemporaryDirectory() as folder:
            manager = SimpleNamespace(dataset=self.dataset,season=2026,batches=[self.batch],batch_sources=[],lock=threading.RLock(),
                                      line_tracker=LineTracker(Path(folder)/"lines.db"),card_path=Path(folder)/"card.json")
            feed = SeasonPerformance(manager,ttl=0)
            with patch("nfl_predictor.server.fetch_week",side_effect=RuntimeError("Unavailable")):
                missing = feed.get()
            self.assertEqual(self.metric(missing,"winner")["unavailable"],5)
            feed.results = copy.deepcopy(self.results)
            with patch("nfl_predictor.server.fetch_week",side_effect=RuntimeError("Unavailable")):
                retained = feed.get()
            self.assertEqual(self.metric(retained,"winner")["decided"],2)
            self.assertEqual(retained["resultSources"][0]["sha256"],"receipt")
            self.assertIn("earlier source time",retained["warnings"][0])

    def test_printed_performance_requires_a_saved_exact_line_pick(self):
        batch = copy.deepcopy(self.batch)
        batch["issued_at"] = "2026-09-02T00:00:00Z"
        card = {"season":2026,"week":1,"received_at":"2026-09-01T12:00:00Z","source":"Supplied printed card","games":[
            {"event_id":g["event_id"],"home":g["home"],"away":g["away"],"line":42.5} for g in self.results[1]["games"][:3]]}
        for row in batch["forecast"]:
            row["kickoff"] = "2026-09-11T00:20:00Z"
            row["total_projection"] = {"total_samples":[30,35,50]}
        self.assertEqual(self.metric(self.payload([batch],cards=[card]),"printed-model")["recorded"],0)
        for row, selection in zip(batch["forecast"],card["games"]):
            row["total_pick"] = saved_total_pick(card,selection,row,batch["issued_at"])
        self.assertEqual(self.metric(self.payload([batch],cards=[card]),"printed-model")["recorded"],3)

    def test_duplicate_result_cannot_overwrite_a_final_score(self):
        results = copy.deepcopy(self.results)
        results[1]["games"].append({**results[1]["games"][0],"home_score":0})
        with self.assertRaises(ValueError):
            self.payload(results=results)
