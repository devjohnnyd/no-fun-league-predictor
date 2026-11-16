"""Update the reviewed dashboard snapshot while preserving app identity."""
import argparse
from pathlib import Path
import json
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--app", type=Path, default=Path("web"))
    parser.add_argument("--complete", action="store_true")
    parser.add_argument("--copy-assets", action="store_true")
    args = parser.parse_args()
    target = args.app / "src/data.json"
    existing = json.loads(target.read_text(encoding="utf-8"))
    reviewed = json.loads(args.snapshot.read_text(encoding="utf-8"))
    reviewed.update(id=existing["id"], surface="dashboard", buildStatus="complete" if args.complete else "creating",
                    extensions={"nflLiveFeed": {"endpoint": "./live-week.json", "intervalMs": 60000}}, filters=[])
    target.write_text(json.dumps(reviewed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.copy_assets:
        source = args.app.parent / "assets/team-logos"
        destination = args.app / "dist/team-logos"
        destination.mkdir(parents=True, exist_ok=True)
        for asset in source.iterdir():
            if asset.is_file():
                shutil.copy2(asset, destination / asset.name)


if __name__ == "__main__":
    main()
