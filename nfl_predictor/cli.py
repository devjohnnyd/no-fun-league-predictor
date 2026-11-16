import argparse
import json
from pathlib import Path

from .evaluate import evaluate
from .freshness import check_pregame
from .sources import refresh
from .tracking import score_batch


def read(path):
    return json.loads(path.read_text())


def save_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description="Reproducible NFL research and pregame checks")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)
    ev = sub.add_parser("evaluate", help="Tune 2024, select 2025, diagnose 2026")
    ev.add_argument("--output", type=Path, required=True)
    rf = sub.add_parser("refresh", help="Fetch current scores and pending Sun/Mon context")
    rf.add_argument("--season", type=int, required=True)
    rf.add_argument("--week", type=int, required=True)
    rf.add_argument("--output", type=Path, required=True)
    sc = sub.add_parser("score", help="Score original probabilities without changing them")
    sc.add_argument("--forecast", type=Path, required=True)
    sc.add_argument("--results", type=Path, required=True)
    sc.add_argument("--output", type=Path, required=True)
    ck = sub.add_parser("check", help="Check freshness and official-lineup evidence")
    ck.add_argument("--manifest", type=Path, required=True)
    ck.add_argument("--final", action="store_true")
    ck.add_argument("--event", help="Check one event, including rejection if it has started")
    ck.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "evaluate":
        result = evaluate(args.root, args.output)
        print(json.dumps({"selected": result["selected"], "diagnostics": result["diagnostics_2026"]}, indent=2))
    elif args.command == "refresh":
        result = refresh(args.season, args.week, args.output)
        print(json.dumps({"games": len(result["games"]), "manifest": str(args.output / "manifest.json")}))
    elif args.command == "score":
        result = score_batch(read(args.forecast), read(args.results))
        save_new(args.output, result)
        print(json.dumps({k: v for k, v in result.items() if k != "games"}, indent=2))
    else:
        manifest = read(args.manifest)
        games = [g for g in manifest["games"] if g.get("slate_eligible", True)
                 and (str(g["event_id"]) == args.event if args.event else g.get("state") == "pre")]
        results = [check_pregame(g, final=args.final) for g in games]
        if args.output:
            save_new(args.output, results)
        print(json.dumps(results, indent=2))
        if not results or any(not r["ready"] for r in results):
            raise SystemExit(1)
