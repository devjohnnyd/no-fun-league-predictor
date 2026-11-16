"""Lagged additions to the frozen v2 feature snapshot. No target-game stats."""

from collections import defaultdict
import json

import numpy as np
import pandas as pd

BASE_NAMES = [
    "home_field", "off_epa_diff", "def_epa_diff", "recent_net_diff", "qb_epa_diff",
    "qb_cpoe_diff", "qb_experience_diff", "qb_new_diff", "sack_rate_diff",
    "def_sack_diff", "explosive_diff", "rest_diff", "new_coach_diff", "ol_out_diff",
    "skill_out_diff", "def_out_diff", "questionable_diff", "wind_pass_diff",
    "cold_pass_diff",
]
PROTECTION = ["hit_allowed_diff", "rush_protection_interaction",
              "ol_absence_rush_interaction"]
CONTINUITY = ["ol_continuity_diff"]
TRANSITION = ["qb_changed_diff", "qb_coach_familiarity_diff"]


def normalize_team(team):
    return {"LA": "LAR", "WAS": "WSH", "OAK": "LV", "SD": "LAC",
            "STL": "LAR"}.get(team, team)


class History:
    def __init__(self, schedule, team_games, qb_games, lineups):
        self.teams = defaultdict(list)
        self.by_game = {g["game_id"]: g for g in schedule}
        self.team_games, self.qb_games, self.lineups = team_games, qb_games, lineups
        for g in sorted(schedule, key=lambda x: (x["season"], x["week"], x["game_id"])):
            if g.get("home_score") is None or g.get("away_score") is None:
                continue
            for side in ("home", "away"):
                self.teams[g[side + "_team"]].append({
                    **g, "qb": g.get(side + "_qb_id"), "coach": g.get(side + "_coach")})

    def prior(self, team, season, week):
        return [g for g in self.teams[team]
                if (g["season"], g["week"]) < (season, week)]

    def protection(self, team, season, week):
        prior = self.prior(team, season, week)
        weighted = [(g, .45) for g in prior if g["season"] == season - 1][-12:]
        weighted += [(g, 1.) for g in prior if g["season"] == season]
        metrics = [(self.team_games[g["game_id"] + "|" + team], weight)
                   for g, weight in weighted]
        def rate(num, den):
            return (sum(m[num] * w for m, w in metrics) + .15 * 100) / (
                sum(m[den] * w for m, w in metrics) + 100)
        return rate("hits", "db"), rate("def_hits", "def_db")

    def continuity(self, team, season, week):
        prior = self.prior(team, season, week)
        # Offseason roster changes are unknown until current-season snaps exist.
        if len(prior) < 2 or prior[-1]["season"] != season:
            return np.nan
        groups = [self.lineups.get(g["game_id"] + "|" + team) for g in prior[-2:]]
        if any(not group or len(group) != 5 for group in groups):
            return np.nan
        return len(set(groups[0]) & set(groups[1])) / 5

    def transition(self, team, qb, coach, season, week):
        prior = self.prior(team, season, week)
        changed = float(qb != prior[-1]["qb"]) if prior and qb and prior[-1]["qb"] else np.nan
        if not qb or not coach:
            return changed, np.nan
        db = 0.
        for item in self.qb_games.get(qb, []):
            if (item["season"], item["week"]) >= (season, week) or item["season"] < season - 2:
                continue
            game = self.by_game.get(item["game_id"])
            if not game:
                continue
            # Assign passer to team using its offensive team-game membership in
            # the derived QB-team map, not the recorded starter (backups matter).
            qb_team = item.get("team")
            side = next((s for s in ("home", "away") if game[s + "_team"] == qb_team), None)
            if side and game.get(side + "_coach") == coach:
                db += item["db"] * .65 ** (season - item["season"])
        return changed, float(np.log1p(db))

    def additions(self, g):
        season, week = int(g["season"]), int(g["week"])
        h, a = g["home_team"], g["away_team"]
        hh, hr = self.protection(h, season, week)
        ah, ar = self.protection(a, season, week)
        hc = self.continuity(h, season, week)
        ac = self.continuity(a, season, week)
        hq, hf = self.transition(h, g.get("home_qb_id"), g.get("home_coach"), season, week)
        aq, af = self.transition(a, g.get("away_qb_id"), g.get("away_coach"), season, week)
        return {"hit_allowed_diff": hh - ah,
                "rush_protection_interaction": hh * ar - ah * hr,
                # v2 has only the net OL load. Interaction with mean rush is
                # deliberately symmetric and does not infer either team's load.
                "ol_absence_rush_interaction": g["ol_out_diff"] * (hr + ar) / 2,
                "ol_continuity_diff": hc - ac,
                "qb_changed_diff": hq - aq,
                "qb_coach_familiarity_diff": hf - af}


def load_features(root):
    archived = root / "archive/session-2026-11-10/enhanced"
    frame = pd.read_csv(archived / "pregame_features.csv",
                        dtype={"home_qb_id": str, "away_qb_id": str, "espn": str})
    frame["espn"] = frame.espn.str.replace(".0", "", regex=False)
    snapshot = json.loads((root / "data/snapshots/history-2026-11-10.json").read_text())
    teams, qbs = {}, defaultdict(list)
    for path in sorted(archived.glob("aggregates_*.json")):
        source = json.loads(path.read_text())
        teams.update(source["team_games"])
        for qb, games in source["qb_games"].items():
            qbs[qb].extend([{**g, "team": snapshot["qb_teams"].get(g["game_id"] + "|" + qb)}
                            for g in games])
    history = History(snapshot["schedule"], teams, qbs, snapshot["lineups"])
    # The schedule's eventual starter must not replace the frozen projected QB.
    frozen = json.loads((archived / "model.json").read_text())
    for forecast in frozen["forecast"]:
        idx = frame.index[frame.game_id.eq(forecast["game_id"])]
        for side in ("home", "away"):
            frame.loc[idx, side + "_qb_id"] = forecast[side + "_qb"]["id"]
    frame = frame.where(pd.notna(frame), None)
    additions = [history.additions(g) for g in frame.to_dict("records")]
    for name in PROTECTION + CONTINUITY + TRANSITION:
        frame[name] = [g[name] for g in additions]
    return frame
