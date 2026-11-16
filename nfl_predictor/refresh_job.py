"""Explicit, serialized refresh of current statistics, context and new forecasts."""
from datetime import datetime, timezone
from pathlib import Path
import json
import threading
import uuid

from .freshness import check_pregame, timestamp
from .storage import read_json, sha256, write_new


class AnalysisRefresh:
    def __init__(self, manager, history_bundles, output):
        self.manager, self.history_bundles, self.output = manager, history_bundles, Path(output)
        self.lock = threading.Lock()
        self.status = {"state": "idle", "message": "Ready to refresh scores, lines and pregame inputs."}
        previous = sorted(self.output.glob("*/status.json"))
        if previous:
            self.status = read_json(previous[-1])

    def start(self, week, *, mode="full", event_ids=None, final=False):
        with self.lock:
            if self.status["state"] == "running":
                return dict(self.status)
            if mode == "full":
                now = datetime.now(timezone.utc)
                budget_path = self.output.parent / "refresh-budget.json"
                budget = read_json(budget_path) if budget_path.is_file() else {}
                if budget.get("date") != now.date().isoformat():
                    budget = {"date": now.date().isoformat(), "count": 0, "last_started": 0}
                if budget["count"] >= 6 or now.timestamp() - budget["last_started"] < 600:
                    return {"state": "blocked", "week": week, "runId": uuid.uuid4().hex,
                            "message": "Full statistics preparation is limited to six runs per UTC day and once per ten minutes. Pregame checks reuse recent fitted models."}
                budget.update(count=budget["count"] + 1, last_started=now.timestamp())
                budget_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = budget_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(budget), encoding="utf-8")
                temporary.replace(budget_path)
            self.status = {"state": "running", "week": week, "runId": uuid.uuid4().hex,
                           "mode": mode, "final": final, "startedAt": datetime.now(timezone.utc).isoformat(),
                           "message": "Refreshing scores and pregame inputs…"}
            threading.Thread(target=self.run, args=(week,), kwargs={"mode": mode, "event_ids": event_ids, "final": final}, daemon=True).start()
            return dict(self.status)

    def cached_models(self, week, now=None):
        """Only reuse exact, verified, recent artifacts for the same cutoff."""
        now = now or datetime.now(timezone.utc)
        for path in sorted(self.output.glob("*/models-ready.json"), reverse=True):
            try:
                ready = read_json(path)
                if (ready["season"], ready["week"]) != (self.manager.season, week):
                    continue
                if not 0 <= (now - timestamp(ready["createdAt"])).total_seconds() < 24 * 3600:
                    continue
                root = path.parent
                if set(ready["files"]) != {"dataset.json.gz", "research/research.json", "totals/totals-model.json"}:
                    continue
                if sha256(self.manager.metadata_path) != ready["venues_sha256"]:
                    continue
                if all(sha256(root / name) == digest for name, digest in ready["files"].items()):
                    return root
            except (OSError, KeyError, ValueError, TypeError):
                continue
        return None

    def receipt(self, run_id):
        for path in sorted(self.output.glob("*/status.json"), reverse=True):
            saved = read_json(path)
            if saved.get("runId") == run_id:
                return saved
        return None

    def run(self, week, *, mode="full", event_ids=None, final=False):
        root = None
        outcome = {}
        self.status.update(state="running", mode=mode, final=final)
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
            if mode not in {"full", "context"}:
                raise ValueError("Unknown analysis refresh mode")
            if not self.history_bundles and not getattr(self.manager, "dataset", None):
                raise ValueError("Fresh scores and lines loaded. Full model refresh requires a historical dataset or source bundle.")
            root = self.output / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            model_root = self.cached_models(week) if mode == "context" else None
            if mode == "context" and model_root is None:
                raise ValueError("Pregame check needs a successful statistics/model preparation within 24 hours; waiting for the next full preparation.")
            if model_root is not None:
                dataset_path = model_root / "dataset.json.gz"
                dataset = read_json(dataset_path)
            else:
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
            if model_root is None:
                self.status.update(message="Fitting chronological winner and total-points models…")
                research(dataset_path, root / "research", self.manager.season, week, self.manager.metadata_path)
                research_totals(dataset_path, self.manager.metadata_path, self.manager.season, week, root / "totals")
                model_root = root
                write_new(root / "models-ready.json", {"season": self.manager.season, "week": week,
                    "createdAt": datetime.now(timezone.utc).isoformat(), "venues_sha256": sha256(self.manager.metadata_path),
                    "files": {name: sha256(root / name) for name in ("dataset.json.gz", "research/research.json", "totals/totals-model.json")}})
            # Prepare AFTER fitting: slow research must not age the feature vector.
            self.status.update(message="Refreshing quarterbacks, injuries, coaches and kickoff weather…")
            options = {"event_ids": set(map(str, event_ids))} if event_ids is not None else {}
            review = self.output.parent / "pregame-review.json"
            if review.is_file():
                options["review_path"] = review
            prepared = prepare(dataset_path, self.manager.metadata_path, self.manager.staff_seed, self.manager.season, week, root / "prepared", **options)
            self.status["inputs"] = [{"eventId": str(g["event_id"]), "sources": g["game"].get("sources", {}),
                                     "check": check_pregame(g["game"], final=final)} for g in prepared["games"] if "game" in g]
            if not any("features" in game for game in prepared["games"]):
                reasons = sorted({reason for game in prepared["games"] for reason in game["preflight"]["reasons"]})
                raise ValueError("No releasable pregame inputs: " + "; ".join(reasons or ["No unstarted games"]))
            self.status.update(message="Checking kickoff and saving new forecast revisions…")
            batch = issue(dataset_path, self.manager.metadata_path, model_root / "research/research.json", root / "prepared/prepared.json", root / "release",
                          totals_model_path=model_root / "totals/totals-model.json", card_path=feed.card_path, final=final)
            if not batch["forecast"]:
                raise ValueError("New forecasts blocked: " + "; ".join(reason for game in batch["blocked"] for reason in game["reasons"]))
            write_new(root / "dataset-reference.json", {"path": str(dataset_path.relative_to(self.output)), "sha256": sha256(dataset_path)})
            self.manager.install(dataset, batch, root / "release/forecast.json")
            outcome = dict(state="complete", message=f"Saved {len(batch['forecast'])} fresh pregame winner and totals projections; {len(batch['blocked'])} blocked games.",
                           releasedGames=len(batch["forecast"]), blockedGames=len(batch["blocked"]),
                           completedAt=datetime.now(timezone.utc).isoformat())
        except Exception as error:
            outcome = dict(state="blocked", message=str(error), completedAt=datetime.now(timezone.utc).isoformat())
        finally:
            finished = {**self.status, **outcome}
            try:
                if root is not None:
                    write_new(root / "status.json", finished)
            except OSError as error:
                finished.update(state="blocked", message=f"Unable to persist preparation receipt: {error}")
            finally:
                # Publish completion only after the immutable receipt is saved.
                with self.lock:
                    self.status = finished
