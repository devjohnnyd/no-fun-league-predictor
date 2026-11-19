from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from nfl_predictor.automation import WeeklyAutomation, planned_jobs
from nfl_predictor.storage import write_new

UTC = timezone.utc


def schedule():
    return {"schedule":[{"season":2026,"week":11,"espn":event,"gameday":day,"gametime":hour,"home_score":None}
                        for event,day,hour in (("Thursday","2026-11-19","20:15"),("Sunday1","2026-11-22","13:00"),
                                               ("Sunday2","2026-11-22","13:00"),("Monday","2026-11-23","20:15"))]}


class AutomationTests(unittest.TestCase):
    def test_schedule_includes_thursday_and_groups_kickoffs_in_utc(self):
        jobs = planned_jobs(schedule(), 2026, datetime(2026,11,19,12,tzinfo=UTC))
        thursday = next(j for j in jobs if j["events"] == ["Thursday"] and not j["final"] and j["mode"] == "context")
        self.assertEqual(datetime.fromtimestamp(thursday["due"],UTC), datetime(2026,11,19,19,15,tzinfo=UTC))
        self.assertTrue(any(j["events"] == ["Sunday1","Sunday2"] for j in jobs))
        self.assertTrue(any(j["events"] == ["Monday"] for j in jobs))

    def test_no_jobs_for_started_completed_or_distant_games(self):
        data = schedule()
        data["schedule"][0]["home_score"] = 20
        jobs = planned_jobs(data,2026,datetime(2026,11,24,12,tzinfo=UTC))
        self.assertEqual(jobs,[])
        self.assertEqual(planned_jobs(data,2026,datetime(2026,10,1,tzinfo=UTC)),[])

    def test_lease_deduplication_retry_and_restart_recovery(self):
        with TemporaryDirectory() as folder:
            now = [datetime(2026,11,18,12,tzinfo=UTC)]
            refresh = SimpleNamespace(status={"state":"idle"}, cached_models=Mock(return_value=None))
            def start(week, **options):
                refresh.status = {"state":"running","week":week,"runId":"run1","message":"Working"}
                return refresh.status
            refresh.start = Mock(side_effect=start)
            manager = SimpleNamespace(dataset=schedule(),season=2026,refresh=refresh)
            first = WeeklyAutomation(manager,Path(folder)/"jobs.db",lambda:now[0])
            first.tick()
            first.tick()
            self.assertEqual(refresh.start.call_count,1)
            second = WeeklyAutomation(manager,Path(folder)/"jobs.db",lambda:now[0])
            second.tick()
            self.assertEqual(refresh.start.call_count,1)
            refresh.status = {"state":"blocked","runId":"run1","message":"Prior game missing"}
            first.tick()
            self.assertEqual(first.status()["recent"][0]["message"],"Prior game missing")
            now[0] += timedelta(minutes=59)
            first.tick()
            self.assertEqual(refresh.start.call_count,1)
            now[0] += timedelta(minutes=1)
            first.tick()
            self.assertEqual(refresh.start.call_count,2)
            # Simulate a crash and a new process after the coordinator lease.
            refresh.status = {"state":"idle"}
            now[0] += timedelta(minutes=6)
            second.tick()
            self.assertIn("Interrupted",second.status()["recent"][0]["message"])

    def test_success_survives_restart_without_duplicate_release(self):
        with TemporaryDirectory() as folder:
            now = [datetime(2026,11,18,12,tzinfo=UTC)]
            refresh = SimpleNamespace(status={"state":"idle"},cached_models=Mock(return_value=None),
                                      start=Mock(return_value={"state":"running","runId":"ok","message":"Working"}))
            manager = SimpleNamespace(dataset=schedule(),season=2026,refresh=refresh)
            first = WeeklyAutomation(manager,Path(folder)/"jobs.db",lambda:now[0])
            first.tick()
            refresh.status = {"state":"complete","runId":"ok","message":"Saved"}
            now[0] += timedelta(minutes=6)
            restarted = WeeklyAutomation(manager,Path(folder)/"jobs.db",lambda:now[0])
            restarted.tick()
            self.assertEqual(refresh.start.call_count,1)
            self.assertEqual(restarted.status()["recent"][0]["state"],"complete")

    def test_final_windows_expire_before_kickoff_and_manual_job_is_respected(self):
        now = datetime(2026,11,20,1,12,tzinfo=UTC)  # Three minutes before TNF
        jobs = planned_jobs(schedule(),2026,now)
        self.assertFalse(any(j["events"] == ["Thursday"] for j in jobs))
        with TemporaryDirectory() as folder:
            refresh = SimpleNamespace(status={"state":"running","runId":"manual"}, start=Mock())
            manager = SimpleNamespace(dataset=schedule(),season=2026,refresh=refresh)
            scheduler = WeeklyAutomation(manager,Path(folder)/"jobs.db",lambda:now)
            scheduler.tick()
            refresh.start.assert_not_called()

    def test_final_check_reuses_models_and_passes_only_the_kickoff_group(self):
        with TemporaryDirectory() as folder:
            now = datetime(2026,11,19,23,45,tzinfo=UTC)
            model = Path(folder)/"models"
            write_new(model/"models-ready.json",{"createdAt":now.isoformat()})
            refresh = SimpleNamespace(status={"state":"idle"},cached_models=Mock(return_value=model),output=Path(folder)/"refreshes",
                                      start=Mock(return_value={"state":"running","runId":"final","message":"Checking"}))
            scheduler = WeeklyAutomation(SimpleNamespace(dataset=schedule(),season=2026,refresh=refresh),Path(folder)/"jobs.db",lambda:now)
            scheduler.tick()
            self.assertFalse(any(c.kwargs.get("final") for c in refresh.start.call_args_list))
            db = sqlite3.connect(Path(folder)/"jobs.db")
            messages = [row[0] or "" for row in db.execute("SELECT message FROM jobs WHERE state='complete'")]
            db.close()
            self.assertTrue(any("no official inactive review" in message for message in messages))
            write_new(Path(folder)/"pregame-review.json",{})
            refresh.start.reset_mock()
            later = WeeklyAutomation(SimpleNamespace(dataset=schedule(),season=2026,refresh=refresh),Path(folder)/"jobs2.db",lambda:now)
            later.tick()
            refresh.start.assert_called_once_with(11,mode="context",event_ids=["Thursday"],final=True)

    def test_partially_blocked_run_retries_only_the_blocked_games(self):
        with TemporaryDirectory() as folder:
            now = [datetime(2026,11,22,12,30,tzinfo=UTC)]  # Sunday 6-hour window
            model = Path(folder)/"models"
            write_new(model/"models-ready.json",{"createdAt":now[0].isoformat()})
            refresh = SimpleNamespace(status={"state":"idle"},cached_models=Mock(return_value=model),output=Path(folder)/"refreshes")
            def start(week, **options):
                refresh.status = {"state":"running","runId":"r%d" % refresh.start.call_count,"message":"Working"}
                return refresh.status
            refresh.start = Mock(side_effect=start)
            scheduler = WeeklyAutomation(SimpleNamespace(dataset=schedule(),season=2026,refresh=refresh),Path(folder)/"jobs.db",lambda:now[0])
            scheduler.tick()
            self.assertEqual(refresh.start.call_args.kwargs["event_ids"],["Sunday1","Sunday2"])
            refresh.status = {"state":"complete","runId":refresh.status["runId"],"message":"Saved 1",
                              "releasedGames":1,"blockedGames":1,"blockedEvents":["Sunday2"]}
            scheduler.tick()  # Records the partial release; the due daily job may start next.
            for _ in range(3):
                refresh.status = {**refresh.status,"state":"complete","releasedGames":1,"blockedGames":0}
                now[0] += timedelta(minutes=10)
                scheduler.tick()
            calls = [c.kwargs["event_ids"] for c in refresh.start.call_args_list]
            self.assertIn(["Sunday2"],calls)
            self.assertEqual(calls.count(["Sunday1","Sunday2"]),1)
