import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from nfl_predictor.line_tracking import LineTracker
from nfl_predictor.market_collection import MarketCollection, active_weeks, collection_interval

UTC = timezone.utc


class MarketCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = datetime(2026,11,16,14,tzinfo=UTC)
        self.root = Path(self.temp.name)
        self.game = {"event_id":"1","home":"BAL","away":"LAC","kickoff":"2026-11-16T19:00:00Z",
                     "state":"pre","completed":False,"total_quotes":[{"book":"Book A","book_id":"A","line":42.5}]}
        self.row = {"season":2026,"week":10,"eventId":"1","homeCode":"BAL","awayCode":"LAC",
                    "kickoff":self.game["kickoff"],"state":"pre","homeScore":None,"awayScore":None}
        self.dataset = {"schedule":[{"season":2026,"week":10,"espn":"1","gameday":"2026-11-16","gametime":"14:00","home_score":None}]}
        self.batch = {"issued_at":"2026-11-16T13:00:00Z","forecast":[{"espn_id":"1","home":"BAL","away":"LAC",
                      "total_projection":{"projected_total":44,"interval_80":[40,48],"total_samples":[43,44,45]}}]}
        self.tracker = LineTracker(self.root/"lines.db")
        self.feed = SimpleNamespace(get=Mock(side_effect=self.payload))
        self.manager = SimpleNamespace(season=2026,dataset=self.dataset,feed=Mock(return_value=self.feed))
        self.collector = MarketCollection(self.manager,self.root/"polls.db",lambda:self.now)

    def payload(self):
        observed = self.now.isoformat()
        value = {"period":{"season":2026,"week":10},"queries":{"matchups":{
            "rows":[copy.deepcopy(self.row)],"source":{"executedAt":observed}}}}
        manifest = {"retrieved_at":observed,"games":[self.game],"scoreboard_source":{"url":"https://example.test/scores","sha256":"abc"}}
        return self.tracker.enrich(value,manifest,[self.batch],now=self.now)

    def status(self):
        return self.collector.status()["weeks"][0]

    def test_background_collection_reanalyzes_movement_and_preserves_original_without_viewers(self):
        self.collector.tick()
        first = self.tracker.export_rows()
        self.now += timedelta(minutes=5)
        self.game["total_quotes"][0]["line"] = 47.5
        self.collector.tick()
        history = self.tracker.export_rows()
        self.assertEqual(len(history),2)
        self.assertEqual(history[0],first[0])
        self.assertIn('"lean": "Over"',history[0]["analysis"])
        self.assertIn('"lean": "Under"',history[1]["analysis"])
        self.assertEqual(self.status()["quotedGames"],1)
        self.assertEqual(self.status()["missingQuotes"],0)
        self.assertEqual(self.status()["lastQuoteAt"],self.now.isoformat())

    def test_restart_keeps_cadence_and_does_not_duplicate_a_poll(self):
        self.collector.tick()
        restarted = MarketCollection(self.manager,self.root/"polls.db",lambda:self.now)
        restarted.tick()
        self.assertEqual(self.feed.get.call_count,1)
        self.assertEqual(restarted.status()["weeks"][0]["lastQuoteAt"],self.now.isoformat())
        self.now += timedelta(minutes=5)
        restarted.tick()
        self.assertEqual(self.feed.get.call_count,2)

    def test_failure_retains_source_times_retries_with_backoff_and_recovers(self):
        self.collector.tick()
        original = self.status()
        self.now += timedelta(minutes=5)
        self.feed.get.side_effect = RuntimeError("Provider unavailable")
        with self.assertLogs("nfl_predictor.market_collection",level="ERROR"):
            self.collector.tick()
        failed = self.status()
        self.assertEqual(failed["state"],"failed")
        self.assertEqual(failed["lastQuoteAt"],original["lastQuoteAt"])
        self.assertEqual(failed["lastSuccessAt"],original["lastSuccessAt"])
        self.now += timedelta(seconds=30)
        self.collector.tick()
        self.assertEqual(self.feed.get.call_count,2)
        self.now += timedelta(seconds=30)
        self.feed.get.side_effect = self.payload
        self.collector.tick()
        self.assertEqual(self.status()["state"],"ok")
        self.assertEqual(self.status()["failures"],0)

    def test_missing_quotes_keep_history_without_claiming_a_current_analysis(self):
        self.collector.tick()
        original = self.status()["lastQuoteAt"]
        self.game["total_quotes"] = []
        self.now += timedelta(minutes=5)
        self.collector.tick()
        self.assertEqual(self.status()["state"],"partial")
        self.assertEqual(self.status()["missingQuotes"],1)
        self.assertEqual(self.status()["lastQuoteAt"],original)
        total = self.payload()["queries"]["matchups"]["rows"][0]["marketTotal"]
        self.assertEqual(total["quoteStatus"],"last observed pregame")
        self.assertIsNone(total["analysis"])
        self.assertEqual(total["originalLine"],42.5)

    def test_live_and_final_scores_never_append_post_kickoff_quotes(self):
        self.collector.tick()
        self.now = datetime(2026,11,16,19,1,tzinfo=UTC)
        self.game.update(state="in")
        self.row.update(state="in",homeScore=21,awayScore=20)
        self.game["total_quotes"][0]["line"] = 80.5
        self.collector.tick()
        self.assertEqual(len(self.tracker.export_rows()),1)
        self.game.update(state="post",completed=True)
        self.row.update(state="post",homeScore=24,awayScore=20)
        self.now += timedelta(minutes=1)
        self.collector.tick()
        self.assertEqual(self.status()["state"],"complete")
        self.assertIsNone(self.status()["nextCheckAt"])
        self.now += timedelta(hours=1)
        self.collector.tick()
        self.assertEqual(self.feed.get.call_count,3)
        self.assertTrue(self.payload()["queries"]["matchups"]["rows"][0]["marketTotal"]["correct"])

    def test_lease_prevents_another_process_polling_and_recovers_after_expiry(self):
        other = MarketCollection(self.manager,self.root/"polls.db",lambda:self.now)
        with self.collector.connect() as db:
            db.execute("INSERT INTO polls(season,week,next_at,lease_owner,lease_until) VALUES(2026,10,0,'old-process',?)",(self.now.timestamp()+120,))
        other.tick()
        self.feed.get.assert_not_called()
        self.now += timedelta(seconds=121)
        other.tick()
        self.feed.get.assert_called_once()

    def test_stale_or_wrong_scope_feed_does_not_advance_success_time(self):
        value = self.payload()
        self.now += timedelta(minutes=3)
        self.feed.get.side_effect = None
        self.feed.get.return_value = value
        with self.assertLogs("nfl_predictor.market_collection",level="ERROR"):
            self.collector.tick()
        self.assertIsNone(self.status()["lastSuccessAt"])
        self.assertEqual(self.status()["state"],"failed")

    def test_adaptive_cadence_and_thursday_schedule_selection(self):
        self.assertEqual(collection_interval([self.row],self.now),300)
        self.assertEqual(collection_interval([self.row],self.now+timedelta(hours=4)),60)
        self.assertEqual(collection_interval([self.row],self.now-timedelta(days=2)),900)
        self.assertEqual(collection_interval([{**self.row,"state":"in"}],self.now),60)
        self.dataset["schedule"].append({"season":2026,"week":11,"espn":"2","gameday":"2026-11-19","gametime":"20:15","home_score":None})
        self.assertEqual(active_weeks(self.dataset,2026,self.now),[10,11])
        self.assertEqual(active_weeks(self.dataset,2026,self.now-timedelta(days=30)),[])
