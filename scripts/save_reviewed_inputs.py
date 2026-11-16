"""Preserve a small pregame evidence package alongside a released forecast."""
import argparse
from pathlib import Path
import shutil

from nfl_predictor.storage import read_json, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepared = read_json(args.prepared)
    args.output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(args.prepared, args.output / "prepared.json")
    write_new(args.output / "reviewed-manifest.json", prepared["scoreboard"])
    for game in prepared["games"]:
        event = game["event_id"]
        for name in (f"summary-{event}.json", f"depth-{event}-home.json", f"depth-{event}-away.json"):
            source = args.prepared.parent / name
            if source.is_file():
                shutil.copy2(source, args.output / name)


if __name__ == "__main__":
    main()
