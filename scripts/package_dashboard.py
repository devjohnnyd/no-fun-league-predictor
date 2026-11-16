"""Bundle a verified static build, official logos and a dated score feed."""
import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--web", type=Path, default=Path("web/dist"))
    parser.add_argument("--logos", type=Path, default=Path("assets/team-logos"))
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    if not snapshot["queries"]["matchups"]["rows"]:
        raise ValueError("Cannot package an empty score feed")
    index = args.web / "index.html"
    if not index.is_file():
        raise ValueError("Build the dashboard first")
    logos = sorted(p for p in args.logos.iterdir() if p.is_file())
    if len(logos) != 32:
        raise ValueError("Expected all 32 official logos")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, "x", compression=ZIP_DEFLATED) as archive:
        archive.write(index, "index.html")
        archive.write(args.snapshot, "live-week.json")
        for logo in logos:
            archive.write(logo, "team-logos/" + logo.name)
        archive.writestr("HOSTING.txt", "Serve this directory over HTTP(S). live-week.json is a dated snapshot.\nFor live updates, replace it with validated exports or proxy the Python backend.\nSee docs/hosting.md and DATA_LICENSES.md in the source repository.\n")
        archive.write(Path(__file__).resolve().parents[1] / "DATA_LICENSES.md", "DATA_LICENSES.md")
    print(f"Packaged {len(logos)} logos and {len(snapshot['queries']['matchups']['rows'])} matchups: {args.output}")


if __name__ == "__main__":
    main()
