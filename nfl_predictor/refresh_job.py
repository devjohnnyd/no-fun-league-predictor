"""Explicit, serialized refresh of current statistics, context and new forecasts."""
from datetime import datetime, timezone
from pathlib import Path
import threading

from .storage import read_json, write_new


class AnalysisRefresh:
    def __init__(self, manager, history_bundles, output):
        self.manager, self.history_bundles, self.output = manager, history_bundles, Path(output)
        self.lock = threading.Lock()
        self.status = {"state": "idle", "message": "Ready to refresh scores, lines and pregame inputs."}
        previous = sorted(self.output.glob("*/status.json"))
        if previous:
            self.status = read_json(previous[-1])

    def start(self, week):
        with self.lock:
            if self.status["state"] == "running":
                return dict(self.status)
            self.status = {"state": "running", "week": week, "message": "Refreshing scores and lines…"}
            threading.Thread(target=self.run, args=(week,), daemon=True).start()
            return dict(self.status)

    def run(self, week):
        root = None
        self.status["week"] = week
        try:
            from .acquire import acquire
            from .dataset import build_dataset, replace_season
            from .engine import FeatureEngine
            from .forecast import issue
            from .live import coverage, prepare
            from .research import research
            from .totals import research_totals
            feed = self.manager.feed(week)
            feed.updated = 0
            feed.get()
            if not self.history_bundles and not getattr(self.manager, "dataset", None):
                raise ValueError("Fresh scores and lines loaded. Full model refresh requires a historical dataset or source bundle.")
            root = self.output / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            self.status.update(message="Downloading current-season statistics…")
            acquire(self.manager.season, self.manager.season, root / "sources")
            self.status.update(message="Validating and rebuilding statistics…")
            dataset_path = root / "dataset.json.gz"
            if self.history_bundles:
                dataset = build_dataset([*self.history_bundles, root / "sources"], dataset_path, end=self.manager.season)
            else:
                current = build_dataset([root / "sources"], root / "current-season.json.gz", start=self.manager.season, end=self.manager.season)
                dataset = replace_season(self.manager.dataset, current, self.manager.season)
                write_new(dataset_path, dataset)
            complete = coverage(FeatureEngine(dataset, self.manager.metadata), self.manager.season, week)
            if not complete["complete"]:
                count = len(complete["missing_games"])
                raise ValueError(f"New statistics downloaded, but {count} prior {'game still lacks' if count == 1 else 'games still lack'} complete results/statistics. New picks are blocked until the provider publishes them.")
            self.status.update(message="Refreshing quarterbacks, injuries, coaches and kickoff weather…")
            prepared = prepare(dataset_path, self.manager.metadata_path, self.manager.staff_seed, self.manager.season, week, root / "prepared")
            if not any("features" in game for game in prepared["games"]):
                reasons = sorted({reason for game in prepared["games"] for reason in game["preflight"]["reasons"]})
                raise ValueError("No releasable pregame inputs: " + "; ".join(reasons or ["No unstarted games"]))
            self.status.update(message="Fitting chronological winner and total-points models…")
            research(dataset_path, root / "research", self.manager.season, week, self.manager.metadata_path)
            research_totals(dataset_path, self.manager.metadata_path, self.manager.season, week, root / "totals")
            self.status.update(message="Checking kickoff and saving new forecast revisions…")
            batch = issue(dataset_path, self.manager.metadata_path, root / "research/research.json", root / "prepared/prepared.json", root / "release",
                          totals_model_path=root / "totals/totals-model.json", card_path=feed.card_path)
            if not batch["forecast"]:
                raise ValueError("New forecasts blocked: " + "; ".join(reason for game in batch["blocked"] for reason in game["reasons"]))
            self.manager.install(dataset, batch, root / "release/forecast.json")
            self.status.update(state="complete", message=f"Saved {len(batch['forecast'])} fresh pregame winner and totals projections; {len(batch['blocked'])} blocked games.",
                               completedAt=datetime.now(timezone.utc).isoformat())
        except Exception as error:
            self.status.update(state="blocked", message=str(error), completedAt=datetime.now(timezone.utc).isoformat())
        finally:
            if root is not None:
                write_new(root / "status.json", dict(self.status))
