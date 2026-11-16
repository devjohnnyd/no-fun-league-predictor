"""Copy the verified dashboard and exact engine/data into johnnyd.ai's API bundle."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

from nfl_predictor.line_tracking import LineTracker
from nfl_predictor.storage import sha256

ROOT = Path(__file__).resolve().parents[1]


def sync(destination, ledger):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    files = {
        "derived/dataset.json.gz": "data/snapshots/dataset-v4-2026-11-16.json.gz",
        "derived/venues.json": "data/snapshots/venues-v4-2026-11-15.json",
        "derived/staff.json": "archive/session-2026-11-10/enhanced/context.json",
        "forecasts/original.json": "archive/session-2026-11-10/enhanced/model.json",
        "forecasts/monday.json": "reports/2026-11-16-complete/monday-forecast/forecast.json",
        "forecasts/monday-totals.json": "reports/2026-11-16-complete/monday-with-totals/forecast.json",
        "web/index.html": "web/dist/index.html",
        "DATA_LICENSES.md": "DATA_LICENSES.md",
    }
    for path in (ROOT / "nfl_predictor").glob("*.py"):
        files["engine/nfl_predictor/" + path.name] = path.relative_to(ROOT)
    for path in (ROOT / "data/cards").glob("*.json"):
        files["cards/" + path.name] = path.relative_to(ROOT)
    for path in (ROOT / "assets/team-logos").iterdir():
        if path.is_file():
            files["web/team-logos/" + path.name] = path.relative_to(ROOT)
    if len([key for key in files if key.startswith("web/team-logos/")]) != 32:
        raise ValueError("The verified build requires all 32 official team logos")
    for target, source in files.items():
        path = destination / target
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, path)
    observations = LineTracker(ledger).export_rows() if Path(ledger).is_file() else []
    (destination / "line-bootstrap.json").write_text(json.dumps(observations, separators=(",", ":")) + "\n", encoding="utf-8")
    files["line-bootstrap.json"] = None
    revision = subprocess.check_output(["git", "-c", f"safe.directory={ROOT.as_posix()}", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    manifest = {"repository": "https://github.com/devjohnnyd/no-fun-league-predictor", "revision": revision,
                "packagedAt": datetime.now(timezone.utc).isoformat(), "season": 2026, "week": 10,
                "files": {target: sha256(destination / target) for target in files}}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Synced {len(files)} verified files, {len(observations)} original line observations; engine {revision[:7]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, default=ROOT / "work/tracker/lines.sqlite3")
    args = parser.parse_args()
    sync(args.destination, args.ledger)
