"""Validated play/game aggregates shared by retrospective and pregame features."""
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .features import normalize_team
from .storage import clean, read_json, sha256, write_new

PBP_COLUMNS = set("play_id game_id posteam defteam season_type week season play_type epa qb_epa qb_dropback qb_kneel qb_spike passer_player_id rusher_player_id receiver_player_id cpoe sack interception qb_hit yards_gained pass rush pass_oe air_yards complete_pass touchdown down qtr score_differential drive yardline_100 game_date home_score away_score field_goal_result kick_distance kicker_player_id temp wind roof".split())
CHART = ["is_motion", "is_play_action", "is_screen_pass", "is_rpo", "is_interception_worthy",
         "is_catchable_ball", "is_drop", "is_qb_fault_sack", "n_blitzers", "n_pass_rushers"]


def unique(frame, keys, label):
    """Exact duplicates may be repeated exports; conflicting records are errors."""
    frame = frame.drop_duplicates()
    if frame.duplicated(keys).any():
        raise ValueError(f"Conflicting duplicate {label}: {keys}")
    return frame


def _csv(path, **kwargs):
    return pd.read_csv(path, low_memory=False, **kwargs)


def _sum(frame, column):
    return float(frame[column].sum())


def offensive_stats(frame):
    passing = frame[frame.qb_dropback.eq(1)]
    rushing = frame[~frame.qb_dropback.eq(1)]
    early = frame[frame.down.isin([1, 2]) & frame.qtr.le(3) & frame.score_differential.abs().le(16)]
    deep = passing[passing.air_yards.ge(20)]
    charted = frame[frame.n_pass_rushers.notna()]
    cp = passing[passing.n_pass_rushers.notna()]
    blitz = cp[cp.n_blitzers.gt(0)]
    result = {
        "plays": len(frame), "epa": _sum(frame, "epa"), "success": int(frame.epa.gt(0).sum()),
        "db": len(passing), "pass_epa": _sum(passing, "epa"), "runs": len(rushing), "rush_epa": _sum(rushing, "epa"),
        "sacks": _sum(passing, "sack"), "hits": _sum(passing, "qb_hit"),
        "explosives": int(((frame["pass"].eq(1) & frame.yards_gained.ge(20)) |
                           (frame["rush"].eq(1) & frame.yards_gained.ge(10))).sum()),
        "early_n": len(early), "early_epa": _sum(early, "epa"), "early_success": int(early.epa.gt(0).sum()),
        "deep_n": len(deep), "deep_epa": _sum(deep, "epa"),
        "air_n": int(passing.air_yards.notna().sum()), "air_sum": _sum(passing, "air_yards"),
        "proe_n": int(frame.pass_oe.notna().sum()), "proe_sum": _sum(frame, "pass_oe"),
        "chart_n": len(charted), "chart_db": len(cp), "motion": _sum(charted, "is_motion"),
        "play_action": _sum(cp, "is_play_action"), "screen": _sum(cp, "is_screen_pass"),
        "rpo": _sum(charted, "is_rpo"), "blitz_db": len(blitz), "blitz_epa": _sum(blitz, "epa"),
    }
    for label, condition in [("pa", cp.is_play_action.eq(1)), ("motion_pass", cp.is_motion.eq(1)), ("screen_pass", cp.is_screen_pass.eq(1))]:
        subset = cp[condition]
        result[label + "_db"] = len(subset)
        result[label + "_epa"] = _sum(subset, "epa")
    return result


def build_dataset(bundles, output, start=2022, end=2026):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    files, receipts = {}, []
    for bundle in map(Path, bundles):
        manifest = read_json(bundle / "sources.json")
        for receipt in manifest["sources"]:
            if receipt["status"] != "ok":
                continue
            path = bundle / receipt["file"]
            if sha256(path) != receipt["sha256"]:
                raise ValueError("Source checksum mismatch: " + path.name)
            files[path.name] = path
            receipts.append(receipt)
    schedule = _csv(files["schedule.csv"], dtype={"espn": str, "home_qb_id": str, "away_qb_id": str})
    schedule = unique(schedule[schedule.game_type.eq("REG") & schedule.season.between(start, end)], ["game_id"], "schedule")
    for side in ("home", "away"):
        schedule[side + "_team"] = schedule[side + "_team"].map(normalize_team)
    schedule["espn"] = schedule.espn.str.replace(".0", "", regex=False)
    # Retain necessary context; betting lines are benchmark-only, never feature inputs.
    schedule_columns = "game_id season week gameday gametime weekday home_team away_team home_score away_score location home_qb_id away_qb_id home_qb_name away_qb_name home_coach away_coach home_rest away_rest roof temp wind espn stadium_id stadium home_moneyline away_moneyline".split()
    games = clean(schedule[schedule_columns].to_dict("records"))
    by_id = {g["game_id"]: g for g in games}
    players = _csv(files["players.csv"], dtype={"gsis_id": str, "espn_id": str, "pfr_id": str})
    players = unique(players[players.gsis_id.notna()], ["gsis_id"], "player identities")
    player_cols = ["gsis_id", "display_name", "position", "espn_id", "pfr_id"]
    identities = clean(players[player_cols].to_dict("records"))
    pfr_to_gsis = {p["pfr_id"]: p["gsis_id"] for p in identities if p["pfr_id"]}
    teams, qbs, snaps, injuries, ngs, kicks = [], [], [], [], [], []
    quality = {"seasons": {}, "injury_conflicts_excluded": 0, "pfr_unmapped": 0,
               "snap_unmapped": 0, "snap_rows": 0, "ngs_week_zero_excluded": 0,
               "invalid_pressure_rows_excluded": []}
    for season in range(start, end + 1):
        pbp = _csv(files[f"pbp_{season}.csv.gz"], usecols=lambda c: c in PBP_COLUMNS)
        required = PBP_COLUMNS - {"qb_epa", "cpoe", "pass_oe"}
        if required - set(pbp):
            raise ValueError(f"PBP {season} schema missing {sorted(required - set(pbp))}")
        pbp = pbp[pbp.season_type.eq("REG") & pbp.game_id.isin(by_id)].copy()
        pbp = unique(pbp, ["game_id", "play_id"], "plays")
        for col in ("posteam", "defteam"):
            pbp[col] = pbp[col].map(normalize_team)
        for col in ("qb_epa", "cpoe", "pass_oe"):
            if col not in pbp:
                pbp[col] = np.nan
        chart_path = files.get(f"ftn_{season}.csv")
        if chart_path:
            chart = _csv(chart_path)
            chart = unique(chart, ["nflverse_game_id", "nflverse_play_id"], "FTN charting")
            chart = chart.rename(columns={"nflverse_game_id": "game_id", "nflverse_play_id": "play_id"})
            pbp = pbp.merge(chart[["game_id", "play_id"] + CHART], on=["game_id", "play_id"], how="left", validate="one_to_one")
        else:
            for col in CHART:
                pbp[col] = np.nan
        for col in CHART:
            # Booleans may be object after the left join, but missing stays missing.
            pbp[col] = pd.to_numeric(pbp[col], errors="coerce")
        eligible = pbp.play_type.isin(["pass", "run"]) & pbp.qb_kneel.ne(1) & pbp.qb_spike.ne(1) & pbp.epa.notna() & pbp.posteam.notna() & pbp.defteam.notna()
        plays = pbp[eligible].copy()
        for gid, group in plays.groupby("game_id", sort=False):
            game = by_id[gid]
            scores = pbp[pbp.game_id.eq(gid)][["home_score", "away_score"]].iloc[0]
            if (game["home_score"], game["away_score"]) != (scores.home_score, scores.away_score):
                raise ValueError("Schedule/PBP score conflict: " + gid)
            all_game = pbp[pbp.game_id.eq(gid)]
            special = all_game[all_game.play_type.isin(["punt", "kickoff", "field_goal", "extra_point"]) & all_game.epa.notna()]
            for team in (game["home_team"], game["away_team"]):
                off, defense = group[group.posteam.eq(team)], group[group.defteam.eq(team)]
                if off.empty or defense.empty:
                    raise ValueError("Missing offensive/defensive plays: " + gid + " " + team)
                starts = off.sort_values("play_id").groupby("drive").first()
                team_special = special[special.posteam.eq(team)]
                opp_special = special[special.defteam.eq(team)]
                teams.append({"game_id": gid, "team": team, "season": season, "week": int(game["week"]),
                              **offensive_stats(off), **{"def_" + k: v for k, v in offensive_stats(defense).items()},
                              "special_epa": _sum(team_special, "epa") - _sum(opp_special, "epa"),
                              "special_n": len(team_special) + len(opp_special),
                              "start_yards": float((100 - starts.yardline_100).sum()),
                              "drives": int(starts.yardline_100.notna().sum())})
        passing = plays[plays.qb_dropback.eq(1)].copy()
        passing["pid"] = passing.passer_player_id.fillna(passing.rusher_player_id)
        passing["qb_value"] = passing.qb_epa.fillna(passing.epa)
        pfr_path = files.get(f"pfr_pass_{season}.csv")
        pfr_map = {}
        if pfr_path:
            pfr = _csv(pfr_path)
            pfr = pfr[pfr.game_type.eq("REG")].copy()
            pfr["pid"] = pfr.pfr_player_id.map(pfr_to_gsis)
            quality["pfr_unmapped"] += int(pfr.pid.isna().sum())
            pfr = unique(pfr[pfr.pid.notna()], ["game_id", "pid"], "PFR weekly passing")
            pfr_map = {(r["game_id"], r["pid"]): r for r in pfr.to_dict("records")}
        for (gid, pid), group in passing[passing.pid.notna()].groupby(["game_id", "pid"], sort=False):
            if group.posteam.nunique() != 1:
                raise ValueError("Ambiguous QB team")
            cp = group[group.n_pass_rushers.notna()]
            blitz = cp[cp.n_blitzers.gt(0)]
            adv = pfr_map.get((gid, pid), {})
            pressure = adv.get("times_pressured")
            pressure_pct = adv.get("times_pressured_pct")
            valid_pressure = (pressure is not None and pd.notna(pressure) and pressure >= 0
                              and pressure_pct is not None and pd.notna(pressure_pct) and 0 <= pressure_pct <= 1
                              and adv.get("times_sacked", 0) <= pressure)
            if adv and not valid_pressure:
                quality["invalid_pressure_rows_excluded"].append({"game_id": gid, "pid": pid,
                    "pressure_count": pressure, "reported_fraction": pressure_pct})
            row = {"game_id": gid, "pid": pid, "team": group.posteam.iloc[0], "season": season, "week": int(group.week.iloc[0]),
                   "db": len(group), "epa": _sum(group, "qb_value"), "cpoe_sum": _sum(group, "cpoe"), "cpoe_n": int(group.cpoe.notna().sum()),
                   "sacks": _sum(group, "sack"), "ints": _sum(group, "interception"), "chart_db": len(cp),
                   "int_worthy": _sum(cp, "is_interception_worthy"), "catchable": _sum(cp, "is_catchable_ball"),
                   "drops": _sum(cp, "is_drop"), "fault_sacks": _sum(cp, "is_qb_fault_sack"),
                   "blitz_db": len(blitz), "blitz_epa": _sum(blitz, "epa"),
                   "pressure_n": pressure if valid_pressure else None, "pfr_db": len(group) if valid_pressure else 0,
                   "pressure_weighted": pressure_pct * len(group) if valid_pressure else None,
                   "pfr_sacks": adv.get("times_sacked") if valid_pressure else None, "bad_throws": adv.get("passing_bad_throws")}
            qbs.append(row)
        fg = pbp[pbp.play_type.eq("field_goal") & pbp.field_goal_result.isin(["made", "missed", "blocked"]) & pbp.kick_distance.notna()]
        kicks += clean(fg[["game_id", "posteam", "kicker_player_id", "kick_distance", "field_goal_result", "temp", "wind", "roof"]].to_dict("records"))
        snap = _csv(files[f"snaps_{season}.csv"])
        snap = snap[snap.game_type.eq("REG") & snap.game_id.isin(by_id)].copy()
        snap["team"] = snap.team.map(normalize_team)
        snap["pid"] = snap.pfr_player_id.map(pfr_to_gsis)
        quality["snap_unmapped"] += int(snap.pid.isna().sum())
        quality["snap_rows"] += len(snap)
        if ((snap.offense_pct < 0) | (snap.offense_pct > 1) | (snap.defense_pct < 0) | (snap.defense_pct > 1)).any():
            raise ValueError("Snap share is not in fraction units")
        snap = unique(snap[snap.pid.notna()], ["game_id", "team", "pid"], "snap counts")
        snaps += clean(snap[["game_id", "team", "pid", "position", "offense_pct", "defense_pct"]].values.tolist())
        inj_path = files.get(f"injuries_{season}.csv")
        if inj_path:
            injury = _csv(inj_path)
            injury = injury[injury.game_type.eq("REG")].copy()
            injury["team"] = injury.team.map(normalize_team)
            cols = ["season", "week", "team", "gsis_id", "position", "report_status"]
            injury = injury[cols].drop_duplicates()
            conflict = injury.duplicated(["season", "week", "team", "gsis_id"], keep=False)
            quality["injury_conflicts_excluded"] += int(conflict.sum())
            injuries += clean(injury[~conflict].to_dict("records"))
        quality["seasons"][str(season)] = {"pbp_games": int(plays.game_id.nunique()), "eligible_plays": len(plays),
                                          "charted_plays": int(plays.n_pass_rushers.notna().sum()), "qb_rows": int(passing.pid.nunique())}
        print(f"Aggregated {season}: {plays.game_id.nunique()} games", flush=True)
    for kind in ("passing", "receiving", "rushing"):
        path = files.get(f"ngs_{kind}.csv.gz") or files.get(f"ngs_{kind}.csv")
        if not path:
            quality["ngs_" + kind] = "missing"
            continue
        frame = _csv(path, dtype={"player_gsis_id": str})
        quality["ngs_week_zero_excluded"] += int(frame.week.eq(0).sum())
        frame = frame[frame.season.between(start, end) & frame.week.gt(0) & frame.season_type.eq("REG")].copy()
        frame["team_abbr"] = frame.team_abbr.map(normalize_team)
        frame = unique(frame, ["season", "week", "team_abbr", "player_gsis_id"], "NGS weekly " + kind)
        wanted = [c for c in ["season", "week", "team_abbr", "player_gsis_id", "attempts", "targets", "rush_attempts", "avg_time_to_throw", "avg_separation", "avg_yac_above_expectation", "rush_yards_over_expected", "avg_intended_air_yards"] if c in frame]
        ngs += [{"kind": kind, **r} for r in clean(frame[wanted].to_dict("records"))]
        quality["ngs_" + kind] = len(frame)
    available_ids = {r["game_id"] for r in teams}
    missing = [g["game_id"] for g in games if g["home_score"] is not None and g["game_id"] not in available_ids]
    quality["completed_games_missing_pbp"] = missing
    result = {"schema_version": 4, "created_at": datetime.now(timezone.utc).isoformat(), "sources": receipts,
              "schedule": games, "players": identities, "team_games": clean(teams), "qb_games": clean(qbs),
              "snaps": snaps, "injuries": injuries, "ngs": ngs, "kicks": kicks, "quality": quality,
              "attribution": "FTN Data via nflverse (ftndata.com); charting-derived fields licensed CC-BY-SA 4.0",
              "historical_timing": "Revised public statistics, final injuries, actual starting QBs and observed weather; first-publication times are not fully available. Retrospective results are conditional on these assumptions."}
    write_new(output, result)
    return result


def replace_season(historical, current, season):
    """Refresh one season while retaining prior-season aggregates and provenance."""
    from copy import deepcopy
    result = deepcopy(historical)
    result["created_at"] = current["created_at"]
    def row_season(row):
        if isinstance(row, list):  # Compact snap rows begin with game_id.
            return int(row[0].split("_")[0])
        return int(row["season"]) if "season" in row else int(row["game_id"].split("_")[0])
    for key in ("schedule", "team_games", "qb_games", "snaps", "injuries", "ngs", "kicks"):
        if any(row_season(row) != season for row in current[key]):
            raise ValueError("Current-season aggregates contain a different season")
        result[key] = [row for row in historical[key] if row_season(row) != season] + current[key]
    result["players"] = current["players"]
    result["sources"] = [*historical["sources"], *current["sources"]]
    result["quality"] = {"historical": historical["quality"], "refreshed_season": season, "current": current["quality"]}
    return result
