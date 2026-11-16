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
    ac = sub.add_parser("acquire", help="Download an immutable historical/current public data bundle")
    ac.add_argument("--start", type=int, default=2022)
    ac.add_argument("--end", type=int, required=True)
    ac.add_argument("--output", type=Path, required=True)
    ac.add_argument("--only", choices=["ngs"])
    ds = sub.add_parser("dataset", help="Validate and aggregate public data for shared historical/live features")
    ds.add_argument("--bundle", type=Path, action="append", required=True)
    ds.add_argument("--start", type=int, default=2022)
    ds.add_argument("--end", type=int, required=True)
    ds.add_argument("--output", type=Path, required=True)
    md = sub.add_parser("metadata", help="Fetch official NFL logos and venue-city metadata")
    md.add_argument("--dataset", type=Path, required=True)
    md.add_argument("--output", type=Path, required=True)
    md.add_argument("--assets", type=Path, required=True)
    rs = sub.add_parser("research", help="Evaluate all v4 families with the shared temporal feature engine")
    rs.add_argument("--dataset", type=Path, required=True)
    rs.add_argument("--venues", type=Path)
    rs.add_argument("--season", type=int, required=True)
    rs.add_argument("--week", type=int, required=True)
    rs.add_argument("--output", type=Path, required=True)
    tr = sub.add_parser("research-totals", help="Fit and chronologically evaluate a separate total-points model")
    tr.add_argument("--dataset", type=Path, required=True)
    tr.add_argument("--venues", type=Path, required=True)
    tr.add_argument("--season", type=int, required=True)
    tr.add_argument("--week", type=int, required=True)
    tr.add_argument("--output", type=Path, required=True)
    pp = sub.add_parser("prepare", help="Refresh evidence and rebuild pregame features from current inputs")
    pp.add_argument("--dataset", type=Path, required=True)
    pp.add_argument("--venues", type=Path, required=True)
    pp.add_argument("--staff-seed", type=Path)
    pp.add_argument("--season", type=int, required=True)
    pp.add_argument("--week", type=int, required=True)
    pp.add_argument("--review", type=Path)
    pp.add_argument("--output", type=Path, required=True)
    fc = sub.add_parser("forecast", help="Release fresh pregame picks with independent benchmarks and shadow candidates")
    fc.add_argument("--dataset", type=Path, required=True)
    fc.add_argument("--venues", type=Path, required=True)
    fc.add_argument("--research", type=Path, required=True)
    fc.add_argument("--prepared", type=Path, required=True)
    fc.add_argument("--output", type=Path, required=True)
    fc.add_argument("--final", action="store_true")
    fc.add_argument("--market-quotes", type=Path, help="Optional timestamped paired American-odds CSV; used only as a benchmark")
    fc.add_argument("--totals-model", type=Path, required=True, help="Separately evaluated total-points model for every game")
    fc.add_argument("--card", type=Path, help="Weekly printed totals; defaults to the matching data/cards file")
    ex = sub.add_parser("export-week", help="Export reviewed matchup rows for the dashboard")
    ex.add_argument("--manifest", type=Path, required=True)
    ex.add_argument("--metadata", type=Path, required=True)
    ex.add_argument("--dataset", type=Path)
    ex.add_argument("--forecast", type=Path, action="append", required=True)
    ex.add_argument("--output", type=Path, required=True)
    ex.add_argument("--card", type=Path, help="Three weekly brochure games; defaults to data/cards/SEASON-weekWEEK.json if present")
    sv = sub.add_parser("serve", help="Serve the dashboard and same-origin live score feed")
    sv.add_argument("--web", type=Path, default=Path("web/dist"))
    sv.add_argument("--metadata", type=Path, required=True)
    sv.add_argument("--dataset", type=Path)
    sv.add_argument("--forecast", type=Path, action="append", required=True)
    sv.add_argument("--logos", type=Path, default=Path("assets/team-logos"))
    sv.add_argument("--season", type=int, required=True)
    sv.add_argument("--week", type=int, required=True)
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=4173)
    sv.add_argument("--card", type=Path)
    sv.add_argument("--state-dir", type=Path, default=Path("work/tracker"), help="Persistent local line history and immutable refresh runs")
    sv.add_argument("--history-bundle", type=Path, action="append", default=[], help="Existing historical raw bundle for full statistical refresh")
    sv.add_argument("--staff-seed", type=Path, default=Path("archive/session-2026-11-10/enhanced/context.json"))
    ev = sub.add_parser("evaluate", help="Tune 2024, select 2025, diagnose 2026")
    ev.add_argument("--output", type=Path, required=True)
    rf = sub.add_parser("refresh", help="Fetch current scores and pregame context for every day of the week")
    rf.add_argument("--season", type=int, required=True)
    rf.add_argument("--week", type=int, required=True)
    rf.add_argument("--output", type=Path, required=True)
    sf = sub.add_parser("scores", help="Fetch current game status and scores without rebuilding predictions")
    sf.add_argument("--season", type=int, required=True)
    sf.add_argument("--week", type=int, required=True)
    sf.add_argument("--output", type=Path, required=True)
    sc = sub.add_parser("score", help="Score original probabilities without changing them")
    sc.add_argument("--forecast", type=Path, required=True)
    sc.add_argument("--results", type=Path, required=True)
    sc.add_argument("--output", type=Path, required=True)
    ct = sub.add_parser("score-card", help="Grade three brochure over/under games without backfilling picks")
    ct.add_argument("--card", type=Path, required=True)
    ct.add_argument("--forecast", type=Path, action="append", required=True)
    ct.add_argument("--results", type=Path, required=True)
    ct.add_argument("--output", type=Path, required=True)
    ck = sub.add_parser("check", help="Check freshness and official-lineup evidence")
    ck.add_argument("--manifest", type=Path, required=True)
    ck.add_argument("--final", action="store_true")
    ck.add_argument("--event", help="Check one event, including rejection if it has started")
    ck.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "acquire":
        from .acquire import acquire
        result = acquire(args.start, args.end, args.output, args.only)
        print(json.dumps({"sources": len(result["sources"]), "errors": [r for r in result["sources"] if r["status"] != "ok"]}, indent=2))
    elif args.command == "dataset":
        from .dataset import build_dataset
        result = build_dataset(args.bundle, args.output, args.start, args.end)
        print(json.dumps(result["quality"], indent=2))
    elif args.command == "metadata":
        from .metadata import acquire_metadata
        result = acquire_metadata(args.dataset, args.output, args.assets)
        print(json.dumps({"teams": len(result["teams"]), "stadiums": len(result["stadiums"]), "errors": result["errors"]}, indent=2))
    elif args.command == "research":
        from .research import research
        result = research(args.dataset, args.output, args.season, args.week, args.venues)
        print(json.dumps({"selected": result["selected"], "excluded": result["excluded_features"]}, indent=2))
    elif args.command == "prepare":
        from .live import prepare
        seed = args.staff_seed or args.root / "archive/session-2026-11-10/enhanced/context.json"
        result = prepare(args.dataset, args.venues, seed, args.season, args.week, args.output, args.review)
        print(json.dumps({"coverage": result["statistics_coverage"], "games": [{"event_id": g["event_id"], "preflight": g["preflight"]} for g in result["games"]]}, indent=2))
    elif args.command == "research-totals":
        from .totals import research_totals
        result = research_totals(args.dataset, args.venues, args.season, args.week, args.output)
        print(json.dumps({"selected": result["selected"], "diagnostic": result["diagnostic"], "baseline": result["mean_baseline_diagnostic"]}, indent=2))
    elif args.command == "forecast":
        from .forecast import issue
        prepared = read(args.prepared)
        card_path = args.card or args.root / f"data/cards/{prepared['season']}-week{prepared['week']}.json"
        result = issue(args.dataset, args.venues, args.research, args.prepared, args.output, args.final, market_path=args.market_quotes, totals_model_path=args.totals_model,
                       card_path=card_path if args.card or card_path.is_file() else None)
        print(json.dumps({"released": len(result["forecast"]), "blocked": result["blocked"]}, indent=2))
        if not result["forecast"]:
            raise SystemExit(1)
    elif args.command == "export-week":
        from .dashboard import week_payload
        from .storage import read_json, write_new
        manifest = read_json(args.manifest)
        card_path = args.card or args.root / f"data/cards/{manifest['season']}-week{manifest['week']}.json"
        result = week_payload(manifest, read_json(args.metadata), [read_json(p) for p in args.forecast], read_json(args.dataset) if args.dataset else None, read_json(card_path) if card_path.is_file() else None)
        write_new(args.output, result)
        print(json.dumps({"games": len(result["queries"]["matchups"]["rows"]), "output": str(args.output)}))
    elif args.command == "serve":
        from .server import serve
        card_path = args.card or args.root / f"data/cards/{args.season}-week{args.week}.json"
        serve(args.web, args.metadata, args.forecast, args.dataset, args.season, args.week, args.host, args.port, args.logos, card_path if card_path.is_file() else None,
              args.state_dir, args.history_bundle, args.staff_seed)
    elif args.command == "evaluate":
        result = evaluate(args.root, args.output)
        print(json.dumps({"selected": result["selected"], "diagnostics": result["diagnostics_2026"]}, indent=2))
    elif args.command == "refresh":
        result = refresh(args.season, args.week, args.output)
        print(json.dumps({"games": len(result["games"]), "manifest": str(args.output / "manifest.json")}))
    elif args.command == "scores":
        from .server import fetch_week
        result = fetch_week(args.season, args.week)
        save_new(args.output, result)
        print(json.dumps({"retrieved_at": result["retrieved_at"], "games": len(result["games"]),
                          "completed": sum(g["completed"] for g in result["games"])}))
    elif args.command == "score":
        result = score_batch(read(args.forecast), read(args.results))
        forecast_snapshot = read(args.forecast)
        if any(row.get("shadow_forecasts") for row in forecast_snapshot["forecast"]):
            from .experiments import score_experiments
            result["experiments"] = score_experiments(forecast_snapshot, read(args.results))
        save_new(args.output, result)
        print(json.dumps({k: v for k, v in result.items() if k != "games"}, indent=2))
    elif args.command == "score-card":
        from .totals import score_card
        result = score_card(read(args.card), [read(path) for path in args.forecast], read(args.results))
        save_new(args.output, result)
        print(json.dumps({key: value for key, value in result.items() if key != "games"}, indent=2))
    else:
        manifest = read(args.manifest)
        games = [g for g in manifest["games"] if (str(g["event_id"]) == args.event if args.event else g.get("state") == "pre")]
        results = [check_pregame(g, final=args.final) for g in games]
        if args.output:
            save_new(args.output, results)
        print(json.dumps(results, indent=2))
        if not results or any(not r["ready"] for r in results):
            raise SystemExit(1)
