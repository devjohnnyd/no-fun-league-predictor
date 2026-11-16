"""Build a compact, versionable snapshot from the original public raw downloads.

Run from the repository root: python scripts/prepare_history.py --raw PATH
This imports local cached files. It does not label them newly fetched.
"""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import pandas as pd


def norm(team):
    return {"LA": "LAR", "WAS": "WSH", "OAK": "LV", "SD": "LAC",
            "STL": "LAR"}.get(team, team)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/snapshots/history-2026-11-10.json"))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    raw = args.raw
    paths = [raw / "schedules.csv"]
    schedule = pd.read_csv(paths[0], dtype={"home_qb_id": str, "away_qb_id": str})
    schedule = schedule[schedule.game_type.eq("REG") & schedule.season.between(2022, 2026)]
    schedule = schedule[schedule.season.lt(2026) | schedule.gameday.le("2026-11-10")]
    for side in ("home", "away"):
        schedule[side + "_team"] = schedule[side + "_team"].map(norm)
    cols = ["game_id", "season", "week", "gameday", "home_team", "away_team",
            "home_qb_id", "away_qb_id", "home_coach", "away_coach", "home_score", "away_score"]
    games = json.loads(schedule[cols].to_json(orient="records"))
    lineups, qb_teams = {}, {}
    for season in range(2023, 2027):
        path = raw / f"snaps_{season}.csv"
        paths.append(path)
        snaps = pd.read_csv(path)
        snaps = snaps[snaps.game_type.eq("REG") & snaps.position.isin(["C", "G", "T", "OT", "OG", "OL"])]
        snaps["team"] = snaps.team.map(norm)
        for (gid, team), group in snaps.groupby(["game_id", "team"]):
            top = group.sort_values(["offense_snaps", "pfr_player_id"], ascending=[False, True])
            top = top[top.offense_snaps.gt(0)].drop_duplicates("pfr_player_id").head(5)
            if len(top) == 5:
                lineups[gid + "|" + team] = top.pfr_player_id.tolist()
    for season in range(2022, 2027):
        path = raw / f"pbp_{season}.csv.gz"
        paths.append(path)
        pbp = pd.read_csv(path, usecols=["game_id", "posteam", "passer_player_id", "rusher_player_id",
                                          "qb_dropback", "season_type"], low_memory=False)
        pbp = pbp[pbp.season_type.eq("REG") & pbp.qb_dropback.eq(1)].copy()
        pbp["qb"] = pbp.passer_player_id.fillna(pbp.rusher_player_id)
        for (gid, qb), group in pbp.dropna(subset=["qb", "posteam"]).groupby(["game_id", "qb"]):
            teams = group.posteam.map(norm).unique()
            if len(teams) != 1:
                raise ValueError(f"Ambiguous QB team: {gid} {qb}")
            qb_teams[gid + "|" + qb] = teams[0]
    result = {
        "as_of": "2026-11-10", "description": "Derived from the original November 10 cache; not a new retrieval",
        "schedule": games, "lineups": lineups, "qb_teams": qb_teams,
        "sources": [
            "https://github.com/nflverse/nfldata/blob/master/data/games.csv",
            "https://github.com/nflverse/nflverse-data/releases/tag/pbp",
            "https://github.com/nflverse/nflverse-data/releases/tag/snap_counts"],
        "raw_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"games": len(games), "lineups": len(lineups), "qb_team_keys": len(qb_teams)}))


if __name__ == "__main__":
    main()
