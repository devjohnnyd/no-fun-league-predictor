"""One prior-week feature engine for research, live predictions and scenarios."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import math

import numpy as np

from .features import BASE_NAMES
from .freshness import timestamp

OUT = {"Out", "Doubtful", "Injured Reserve", "IR", "Suspension", "Inactive"}
RESERVE = {"Injured Reserve", "IR"}
OL = {"C", "G", "T", "OT", "OG", "OL", "LT", "LG", "RG", "RT"}
SKILL = {"RB", "FB", "WR", "TE", "HB"}
SECONDARY = {"CB", "DB", "S", "FS", "SS", "LCB", "RCB", "NB"}
FAMILIES = {
    "opponent_adjustment": ["adj_off_diff", "adj_def_diff", "adj_pass_matchup", "adj_rush_matchup", "early_success_matchup"],
    "replacement_injuries": ["replacement_experience_diff", "skill_quality_loss_diff", "ol_cluster_diff", "secondary_cluster_diff"],
    "qb_decisions": ["int_worthy_diff", "catchable_diff", "drop_diff", "qb_fault_sack_diff", "qb_time_to_throw_diff"],
    "pressure_matchups": ["pressure_allowed_diff", "def_pressure_diff", "pressure_to_sack_diff", "pressure_matchup", "qb_vs_blitz_matchup"],
    "scheme_matchups": ["play_action_matchup", "motion_matchup", "screen_matchup", "deep_pass_matchup"],
    "tracking_skill": ["receiver_separation_diff", "receiver_yac_oe_diff", "rush_yoe_diff"],
    "special_teams": ["special_epa_diff", "starting_field_position_diff", "kicking_residual_diff"],
    "body_clock": ["body_clock_shift_diff", "timezone_crossings_diff", "eastward_shift_diff", "westward_shift_diff", "early_home_clock_diff", "late_home_clock_diff", "rest_adjusted_shift_diff"],
    "travel_weather": ["travel_km_diff", "consecutive_road_diff", "wind_depth_diff", "wind_kicking_diff", "wet_pass_diff"],
}


def position_group(position):
    position = (position or "").upper()
    if position in OL:
        return "OL"
    if position in SECONDARY:
        return "DB"
    if position in {"DE", "DT", "NT", "DL", "LDE", "RDE"}:
        return "DL"
    if "LB" in position or position == "LB":
        return "LB"
    if position.startswith("WR"):
        return "WR"
    return "RB" if position in {"RB", "HB", "FB"} else position


def weighted_rate(items, numerator, denominator, prior=0., strength=100., unknown=False):
    valid = [(r, w) for r, w in items if r.get(numerator) is not None and r.get(denominator) is not None]
    n = sum(r[denominator] * w for r, w in valid)
    if n <= 0 and unknown:
        return None
    return (sum(r[numerator] * w for r, w in valid) + prior * strength) / (n + strength)


def difference(a, b):
    return a - b if a is not None and b is not None else None


def haversine_km(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dlat, dlon = p2 - p1, math.radians(b[1] - a[1])
    q = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1., math.sqrt(q)))


class FeatureEngine:
    def __init__(self, dataset, venues=None):
        self.dataset = dataset
        self.schedule = {g["game_id"]: g for g in dataset["schedule"]}
        self.team_games, self.qb_games, self.snap_games, self.ngs = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
        self.team_by_game = {}
        self.injuries = defaultdict(list)
        self.qbs_by_game_team = defaultdict(list)
        self.players = {p["gsis_id"]: p for p in dataset["players"]}
        self.espn_ids = {str(p["espn_id"]).removesuffix(".0"): p["gsis_id"] for p in dataset["players"] if p.get("espn_id")}
        self.venues = venues or {"stadiums": {}, "team_homes": {}}
        for row in dataset["team_games"]:
            self.team_games[row["team"]].append(row)
            self.team_by_game[(row["game_id"], row["team"])] = row
        for rows in self.team_games.values():
            rows.sort(key=lambda r: (r["season"], r["week"], r["game_id"]))
        for row in dataset["qb_games"]:
            self.qb_games[row["pid"]].append(row)
            self.qbs_by_game_team[(row["game_id"], row["team"])].append(row)
        for row in dataset["snaps"]:
            self.snap_games[(row[0], row[1])].append({"pid": row[2], "position": row[3], "off": row[4], "def": row[5]})
        for row in dataset["ngs"]:
            self.ngs[(row["player_gsis_id"], row["kind"])].append(row)
        for row in dataset["injuries"]:
            self.injuries[(row["season"], row["week"], row["team"])].append({
                "pid": row["gsis_id"], "position": row["position"], "status": row["report_status"]})
        self._states, self._adjusted, self._kicking = {}, {}, {}

    @staticmethod
    def before(row, season, week):
        return (row["season"], row["week"]) < (season, week)

    def history(self, team, season, week):
        return [r for r in self.team_games[team] if self.before(r, season, week)]

    def weighted(self, team, season, week):
        history = self.history(team, season, week)
        return ([(r, .45) for r in history if r["season"] == season - 1][-12:] +
                [(r, 1.) for r in history if r["season"] == season])

    def team_state(self, team, season, week):
        key = team, season, week
        if key in self._states:
            return self._states[key]
        weighted = self.weighted(team, season, week)
        rate = lambda n, d, prior=0., unknown=False: weighted_rate(weighted, n, d, prior, unknown=unknown)
        recent = [(r, 1.) for r in self.history(team, season, week)[-4:]]
        state = {
            "off_epa": rate("epa", "plays"), "def_epa": rate("def_epa", "def_plays"),
            "pass_epa": rate("pass_epa", "db"), "def_pass_epa": rate("def_pass_epa", "def_db"),
            "rush_epa": rate("rush_epa", "runs"), "def_rush_epa": rate("def_rush_epa", "def_runs"),
            "recent_net": weighted_rate(recent, "epa", "plays") - weighted_rate(recent, "def_epa", "def_plays"),
            "sack_rate": rate("sacks", "db", .065), "def_sack_rate": rate("def_sacks", "def_db", .065),
            "explosive": rate("explosives", "plays", .10), "pass_rate": rate("db", "plays", .60),
            "early_success": rate("early_success", "early_n", .43), "def_early_success": rate("def_early_success", "def_early_n", .43),
            "air_depth": rate("air_sum", "air_n", 7., unknown=True),
            "special_epa": rate("special_epa", "special_n", unknown=True),
            "start_yards": rate("start_yards", "drives", 28., unknown=True),
            "play_action": rate("play_action", "chart_db", .20, True), "motion": rate("motion", "chart_n", .40, True),
            "screen": rate("screen", "chart_db", .10, True), "def_blitz": rate("def_blitz_db", "def_chart_db", .25, True),
            "deep_epa": rate("deep_epa", "deep_n", 0., True), "def_deep_epa": rate("def_deep_epa", "def_deep_n", 0., True),
            "prior_plays": sum(r["plays"] * w for r, w in weighted),
        }
        for label in ("pa", "motion_pass", "screen_pass"):
            state["def_" + label + "_epa"] = rate("def_" + label + "_epa", "def_" + label + "_db", 0., True)
        pressure_rows = []
        for game_row, weight in weighted:
            game = self.schedule[game_row["game_id"]]
            opponent = game["away_team"] if team == game["home_team"] else game["home_team"]
            quarterbacks = self.qbs_by_game_team[(game_row["game_id"], opponent)]
            pressure_rows.append(({"pressure": sum(r.get("pressure_weighted") or 0 for r in quarterbacks),
                                   "exposure": sum(r.get("pfr_db", 0) for r in quarterbacks)}, weight))
        state["def_pressure"] = weighted_rate(pressure_rows, "pressure", "exposure", .25, unknown=True)
        # Charted scheme performance is computed by conditioning offense and
        # defense on those same prior plays, rather than inventing coach grades.
        self._states[key] = state
        return state

    def qb_state(self, pid, season, week):
        history = [(r, .65 ** (season - r["season"])) for r in self.qb_games.get(pid, [])
                   if self.before(r, season, week) and r["season"] >= season - 2]
        n = sum(r["db"] * w for r, w in history)
        rate = lambda num, den, prior=0., strength=100.: weighted_rate(history, num, den, prior, strength, unknown=True)
        ngs = self.ngs_rate(pid, "passing", "avg_time_to_throw", "attempts", season, week)
        return {"id": pid, "name": self.players.get(pid, {}).get("display_name", "Unknown QB"), "effective_dropbacks": n,
                "epa": weighted_rate(history, "epa", "db", 0., 150.),
                "cpoe": weighted_rate(history, "cpoe_sum", "cpoe_n", 0., 100.),
                "experience": math.log1p(n), "new": int(n < 30),
                "int_worthy": rate("int_worthy", "chart_db", .025), "catchable": rate("catchable", "chart_db", .70),
                "drops": rate("drops", "chart_db", .04), "fault_sacks": rate("fault_sacks", "chart_db", .02),
                "pressure_allowed": rate("pressure_weighted", "pfr_db", .25),
                "pressure_to_sack": rate("pfr_sacks", "pressure_n", .20, 30.),
                "blitz_epa": rate("blitz_epa", "blitz_db"), "time_to_throw": ngs,
                "chart_dropbacks": sum(r["chart_db"] * w for r, w in history),
                "pfr_dropbacks": sum(r.get("pfr_db", 0) * w for r, w in history)}

    def ngs_rate(self, pid, kind, value, denominator, season, week, total=False):
        rows = [(r, .65 ** (season - r["season"])) for r in self.ngs.get((pid, kind), [])
                if self.before(r, season, week) and r["season"] >= season - 1 and r.get(value) is not None and r.get(denominator)]
        n = sum(r[denominator] * w for r, w in rows)
        if not n:
            return None
        numerator = sum(r[value] * (1 if total else r[denominator]) * w for r, w in rows)
        # Neutral shrinkage is appropriate for above-expectation metrics;
        # raw separation/time metrics retain their observed weighted mean.
        return numerator / (n + (30 if "expectation" in value or "over_expected" in value else 0))

    def opponent_ratings(self, season, week):
        key = season, week
        if key in self._adjusted:
            return self._adjusted[key]
        rows = [(r, w) for team in self.team_games for r, w in self.weighted(team, season, week)]
        codes = sorted(self.team_games)
        index = {t: i for i, t in enumerate(codes)}
        result = {t: {} for t in codes}
        for label, numerator, denominator in (("all", "epa", "plays"), ("pass", "pass_epa", "db"), ("rush", "rush_epa", "runs"), ("early", "early_epa", "early_n")):
            valid = [(r, w) for r, w in rows if r[denominator] > 0]
            if not valid:
                for t in codes:
                    result[t][label] = {"off": None, "def": None}
                continue
            x = np.zeros((len(valid), 1 + 2 * len(codes)))
            y, weights = [], []
            for i, (row, weight) in enumerate(valid):
                game = self.schedule[row["game_id"]]
                opponent = game["away_team"] if row["team"] == game["home_team"] else game["home_team"]
                x[i, 0] = 1
                x[i, 1 + index[row["team"]]] = 1
                x[i, 1 + len(codes) + index[opponent]] = 1
                y.append(row[numerator] / row[denominator])
                weights.append(row[denominator] * weight)
            weights = np.asarray(weights)
            penalty = np.eye(x.shape[1]) * 300.
            penalty[0, 0] = 1e-6
            beta = np.linalg.solve((x.T * weights) @ x + penalty, x.T @ (weights * y))
            for team, i in index.items():
                result[team][label] = {"off": float(beta[1 + i]), "def": float(beta[1 + len(codes) + i])}
        self._adjusted[key] = result
        return result

    def recent_roles(self, team, season, week):
        games = self.history(team, season, week)[-4:]
        roles = {}
        for game in games:
            for row in self.snap_games[(game["game_id"], team)]:
                pid = row["pid"]
                roles.setdefault(pid, {"pid": pid, "position": row["position"], "off": 0., "def": 0.})
                for field in ("off", "def"):
                    roles[pid][field] += (row.get(field) or 0.) / len(games)
        return roles

    def injuries_state(self, team, season, week, live=None):
        rows = live if live is not None else self.injuries.get((season, week, team), [])
        roles = self.recent_roles(team, season, week)
        unavailable = {r["pid"] for r in rows if r.get("status") in OUT and r.get("pid")}
        state = {"ol_out": 0., "skill_out": 0., "def_out": 0., "questionable": 0.,
                 "ol_cluster": 0, "secondary_cluster": 0, "replacement_experience": 0.,
                 "skill_quality_loss": None, "reports": [], "unmapped": 0}
        quality_losses = []
        replacement_unknown, quality_unknown = False, False
        primary_count = {"OL": 5, "WR": 3, "TE": 1, "RB": 1, "DB": 5, "DL": 4, "LB": 3}
        for injury in rows:
            # Training practice reports never list reserve players, so live reserve rows stay out of the workload features.
            if injury.get("status") not in OUT | {"Questionable"} or injury.get("status") in RESERVE or position_group(injury.get("position")) == "QB":
                continue
            pid = injury.get("pid")
            group = position_group(injury.get("position"))
            if not pid or pid not in roles:
                state["unmapped"] += 1
            role = roles.get(pid, {"off": 0., "def": 0.})
            workload = role["off"] if group in {"OL", "WR", "RB", "TE"} else role["def"]
            report = {**injury, "recent_role": workload, "replacement": None, "replacement_role": None}
            if injury["status"] == "Questionable":
                state["questionable"] += workload
                state["reports"].append(report)
                continue
            state["ol_out" if group == "OL" else "skill_out" if group in {"WR", "TE", "RB"} else "def_out"] += workload
            if workload >= .4:
                state["ol_cluster"] += int(group == "OL")
                state["secondary_cluster"] += int(group == "DB")
            candidates = sorted([r for r in roles.values() if position_group(r["position"]) == group],
                                key=lambda r: max(r["off"], r["def"]), reverse=True)
            starters = {r["pid"] for r in candidates[:primary_count.get(group, 1)]}
            # This historical proxy is explicit; live depth slots can supply an
            # actual replacement override without using target-game snaps.
            replacement = next((r for r in candidates if r["pid"] not in unavailable and r["pid"] not in starters), None)
            override = injury.get("replacement_pid")
            if override:
                replacement = roles.get(override, {"pid": override, "off": 0., "def": 0.})
            if workload and replacement is None:
                replacement_unknown = True
                quality_unknown = quality_unknown or group in {"WR", "TE", "RB"}
            if replacement and workload:
                replacement_role = max(replacement["off"], replacement["def"])
                state["replacement_experience"] += workload - replacement_role
                report.update(replacement=replacement["pid"], replacement_role=replacement_role)
                if group in {"WR", "TE", "RB"}:
                    kind, value, den = ("rushing", "rush_yards_over_expected", "rush_attempts") if group == "RB" else ("receiving", "avg_yac_above_expectation", "targets")
                    own = self.ngs_rate(pid, kind, value, den, season, week, total=group == "RB")
                    other = self.ngs_rate(replacement["pid"], kind, value, den, season, week, total=group == "RB")
                    if own is not None and other is not None:
                        quality_losses.append(workload * (own - other))
                    else:
                        quality_unknown = True
            state["reports"].append(report)
        if quality_unknown:
            state["skill_quality_loss"] = None
        elif quality_losses:
            state["skill_quality_loss"] = sum(quality_losses)
        elif not any(r.get("status") in OUT and position_group(r.get("position")) in {"WR", "TE", "RB"} for r in rows):
            state["skill_quality_loss"] = 0.
        # Unmapped recent losses cannot establish a zero experience gap.
        if replacement_unknown or (state["unmapped"] and not roles):
            state["replacement_experience"] = None
        return state

    def skill_state(self, team, season, week):
        roles = self.recent_roles(team, season, week)
        result = {}
        for label, kind, value, den, total, groups in [
            ("separation", "receiving", "avg_separation", "targets", False, {"WR", "TE"}),
            ("yac_oe", "receiving", "avg_yac_above_expectation", "targets", False, {"WR", "TE"}),
            ("rush_yoe", "rushing", "rush_yards_over_expected", "rush_attempts", True, {"RB"})]:
            samples = [(self.ngs_rate(pid, kind, value, den, season, week, total), role["off"])
                       for pid, role in roles.items() if position_group(role["position"]) in groups]
            samples = [(v, w) for v, w in samples if v is not None and w > 0]
            result[label] = sum(v * w for v, w in samples) / sum(w for _, w in samples) if samples else None
        return result

    def kicking_state(self, season, week, by_player=False):
        key = season, week, by_player
        if key in self._kicking:
            return self._kicking[key]
        rows = [r for r in self.dataset["kicks"] if r["game_id"] in self.schedule and
                self.before(self.schedule[r["game_id"]], season, week) and self.schedule[r["game_id"]]["season"] >= season - 1]
        buckets, cells = defaultdict(list), defaultdict(list)
        def context(row):
            indoors = row.get("roof") in {"dome", "closed"}
            return (min(6, int(row["kick_distance"] // 10)),
                    0 if indoors else int(row["wind"] >= 10) if row.get("wind") is not None else None,
                    0 if indoors else int(row["temp"] < 40) if row.get("temp") is not None else None)
        for row in rows:
            bucket = context(row)
            made = int(row["field_goal_result"] == "made")
            buckets[bucket[0]].append(made)
            cells[bucket].append(made)
        result = defaultdict(list)
        for row in rows:
            bucket = context(row)
            baseline = sum(buckets[bucket[0]]) / len(buckets[bucket[0]])
            values = cells[bucket]
            expected = (sum(values) + 20 * baseline) / (len(values) + 20)
            identity = row.get("kicker_player_id") if by_player else row["posteam"]
            if identity:
                result[identity].append(int(row["field_goal_result"] == "made") - expected)
        states = {team: sum(values) / (len(values) + 20) for team, values in result.items()}
        self._kicking[key] = states
        return states

    def projected_kicker(self, team, season, week):
        unavailable = {r.get("pid") for r in self.injuries.get((season, week, team), []) if r.get("status") in OUT}
        past = [row for row in self.dataset["kicks"] if row.get("posteam") == team and row.get("kicker_player_id")
                and row["kicker_player_id"] not in unavailable
                and self.before(self.schedule[row["game_id"]], season, week)]
        past.sort(key=lambda r: (self.schedule[r["game_id"]]["season"], self.schedule[r["game_id"]]["week"]))
        return past[-1]["kicker_player_id"] if past else None

    def travel_state(self, team, game):
        from zoneinfo import ZoneInfo
        season, week = game["season"], game["week"]
        history = self.history(team, season, week)
        last = self.schedule[history[-1]["game_id"]] if history else None
        road = team != game["home_team"] or game.get("location") == "Neutral"
        consecutive = int(road and last is not None and (last["home_team"] != team or last.get("location") == "Neutral") and last["season"] == season)
        home = self.venues.get("team_homes", {}).get(team)
        venue = self.venues.get("games", {}).get(game["game_id"])
        if venue is None and game.get("location") != "Neutral":
            venue = self.venues.get("stadiums", {}).get(game.get("stadium_id"))
        if not home or not venue:
            return {"km": None, "clock_shift": None, "zones_crossed": None, "eastward": None, "westward": None,
                    "home_clock_kickoff": None, "early_clock": None, "late_clock": None, "rest_adjusted_shift": None,
                    "consecutive_road": consecutive}
        if not game.get("gametime"):
            return {"km": haversine_km((home["latitude"], home["longitude"]), (venue["latitude"], venue["longitude"])),
                    "clock_shift": None, "zones_crossed": None, "eastward": None, "westward": None,
                    "home_clock_kickoff": None, "early_clock": None, "late_clock": None, "rest_adjusted_shift": None,
                    "consecutive_road": consecutive}
        when = datetime.fromisoformat(game["gameday"] + "T" + game["gametime"]).replace(tzinfo=ZoneInfo("America/New_York"))
        origin_time, venue_time = when.astimezone(ZoneInfo(home["timezone"])), when.astimezone(ZoneInfo(venue["timezone"]))
        offset = (venue_time.utcoffset() - origin_time.utcoffset()).total_seconds() / 3600
        # Circadian phase wraps at 24 hours: Melbourne's +17-hour wall-clock
        # offset from California represents a -7-hour phase shift, not 17 hours.
        phase = (offset + 12) % 24 - 12
        hour = origin_time.hour + origin_time.minute / 60
        rest = game.get("home_rest" if team == game["home_team"] else "away_rest")
        return {"km": haversine_km((home["latitude"], home["longitude"]), (venue["latitude"], venue["longitude"])),
                "clock_shift": phase, "utc_offset_difference": offset, "zones_crossed": abs(phase),
                "eastward": max(0., phase), "westward": max(0., -phase),
                "home_clock_kickoff": origin_time.isoformat(), "venue_clock_kickoff": venue_time.isoformat(),
                "early_clock": max(0., 12 - hour), "late_clock": max(0., hour - 20),
                "rest_adjusted_shift": abs(phase) / max(1., rest) if rest is not None else None,
                "consecutive_road": consecutive,
                "meaning": "Home-clock and scheduled-rest proxies; arrival times and actual acclimation are unknown"}

    def features(self, game, live_context=None, scenario=None):
        season, week = int(game["season"]), int(game["week"])
        home, away = game["home_team"], game["away_team"]
        context = live_context or {}
        ht, at = context.get("teams", {}).get(home, {}), context.get("teams", {}).get(away, {})
        hp = ht.get("qb_id") if live_context is not None else game.get("home_qb_id")
        ap = at.get("qb_id") if live_context is not None else game.get("away_qb_id")
        if scenario == "home_backup":
            hp = ht.get("backup_qb_id")
        if scenario == "away_backup":
            ap = at.get("backup_qb_id")
        if live_context is not None and (not hp or not ap):
            raise ValueError("Both projected QB identities must be resolved")
        hrows, arows = ht.get("injuries"), at.get("injuries")
        if scenario == "questionable_out":
            def available_backup(team, rows, starter):
                if not any(r.get("pid") == starter and r.get("status") == "Questionable" for r in rows or []):
                    return starter
                backup = team.get("backup_qb_id")
                unavailable = {r.get("pid") for r in rows or [] if r.get("status") in OUT | {"Questionable"}}
                if not backup or backup == starter or backup in unavailable:
                    raise ValueError("Questionable QB out scenario requires an available verified backup")
                return backup
            hp, ap = available_backup(ht, hrows, hp), available_backup(at, arows, ap)
            hrows = [{**r, "status": "Out" if r.get("status") == "Questionable" else r.get("status")} for r in hrows or []]
            arows = [{**r, "status": "Out" if r.get("status") == "Questionable" else r.get("status")} for r in arows or []]
        hs, aws = self.team_state(home, season, week), self.team_state(away, season, week)
        hq, aq = self.qb_state(hp, season, week), self.qb_state(ap, season, week)
        hi, ai = self.injuries_state(home, season, week, hrows), self.injuries_state(away, season, week, arows)
        hc, ac = ht.get("staff", {}).get("head_coach", game.get("home_coach")), at.get("staff", {}).get("head_coach", game.get("away_coach"))
        old_h = {self.schedule[r["game_id"]]["home_coach" if self.schedule[r["game_id"]]["home_team"] == home else "away_coach"] for r in self.history(home, season, week) if r["season"] == season - 1}
        old_a = {self.schedule[r["game_id"]]["home_coach" if self.schedule[r["game_id"]]["home_team"] == away else "away_coach"] for r in self.history(away, season, week) if r["season"] == season - 1}
        weather = context.get("weather", {})
        if live_context is None:
            outdoor = game.get("roof") in {"outdoors", "open"}
            temperature, wind, wet = game.get("temp"), game.get("wind"), None
        else:
            outdoor = not weather.get("enclosed_verified", False)
            temperature, wind, wet = weather.get("temperature_f"), weather.get("wind_mph"), weather.get("precip_probability")
        if scenario == "roof_open":
            outdoor = True
        if scenario == "roof_closed":
            outdoor = False
        passdiff = hs["pass_rate"] - aws["pass_rate"]
        features = {
            "home_field": 0. if game.get("location") == "Neutral" else 1.,
            "off_epa_diff": hs["off_epa"] - aws["off_epa"], "def_epa_diff": hs["def_epa"] - aws["def_epa"],
            "recent_net_diff": hs["recent_net"] - aws["recent_net"], "qb_epa_diff": hq["epa"] - aq["epa"],
            "qb_cpoe_diff": hq["cpoe"] - aq["cpoe"], "qb_experience_diff": hq["experience"] - aq["experience"],
            "qb_new_diff": hq["new"] - aq["new"], "sack_rate_diff": hs["sack_rate"] - aws["sack_rate"],
            "def_sack_diff": hs["def_sack_rate"] - aws["def_sack_rate"], "explosive_diff": hs["explosive"] - aws["explosive"],
            "rest_diff": max(-7, min(7, (game.get("home_rest") or 7) - (game.get("away_rest") or 7))),
            "new_coach_diff": int(bool(old_h) and hc not in old_h) - int(bool(old_a) and ac not in old_a),
            "ol_out_diff": hi["ol_out"] - ai["ol_out"], "skill_out_diff": hi["skill_out"] - ai["skill_out"],
            "def_out_diff": hi["def_out"] - ai["def_out"], "questionable_diff": hi["questionable"] - ai["questionable"],
            "wind_pass_diff": wind / 15 * passdiff if outdoor and wind is not None else None if outdoor else 0.,
            "cold_pass_diff": max(0, 45 - temperature) / 20 * passdiff if outdoor and temperature is not None else None if outdoor else 0.,
        }
        ratings = self.opponent_ratings(season, week)
        hr, ar = ratings[home], ratings[away]
        hk, ak = self.skill_state(home, season, week), self.skill_state(away, season, week)
        kicker_rates = self.kicking_state(season, week, by_player=True)
        hkid = ht.get("kicker_id") if live_context is not None else self.projected_kicker(home, season, week)
        akid = at.get("kicker_id") if live_context is not None else self.projected_kicker(away, season, week)
        kicking = {home: kicker_rates.get(hkid), away: kicker_rates.get(akid)}
        htravel, atravel = self.travel_state(home, game), self.travel_state(away, game)
        features.update({
            "adj_off_diff": difference(hr["all"]["off"], ar["all"]["off"]),
            "adj_def_diff": difference(hr["all"]["def"], ar["all"]["def"]),
            "adj_pass_matchup": hr["pass"]["off"] + ar["pass"]["def"] - ar["pass"]["off"] - hr["pass"]["def"] if hr["pass"]["off"] is not None else None,
            "adj_rush_matchup": hr["rush"]["off"] + ar["rush"]["def"] - ar["rush"]["off"] - hr["rush"]["def"] if hr["rush"]["off"] is not None else None,
            "early_success_matchup": hs["early_success"] + aws["def_early_success"] - aws["early_success"] - hs["def_early_success"],
            "replacement_experience_diff": difference(hi["replacement_experience"], ai["replacement_experience"]),
            "skill_quality_loss_diff": difference(hi["skill_quality_loss"], ai["skill_quality_loss"]),
            "ol_cluster_diff": hi["ol_cluster"] - ai["ol_cluster"], "secondary_cluster_diff": hi["secondary_cluster"] - ai["secondary_cluster"],
            "int_worthy_diff": difference(hq["int_worthy"], aq["int_worthy"]), "catchable_diff": difference(hq["catchable"], aq["catchable"]),
            "drop_diff": difference(hq["drops"], aq["drops"]), "qb_fault_sack_diff": difference(hq["fault_sacks"], aq["fault_sacks"]),
            "qb_time_to_throw_diff": difference(hq["time_to_throw"], aq["time_to_throw"]),
            "pressure_allowed_diff": difference(hq["pressure_allowed"], aq["pressure_allowed"]),
            "def_pressure_diff": difference(hs["def_pressure"], aws["def_pressure"]),
            "pressure_to_sack_diff": difference(hq["pressure_to_sack"], aq["pressure_to_sack"]),
            "pressure_matchup": hq["pressure_allowed"] * aws["def_pressure"] - aq["pressure_allowed"] * hs["def_pressure"] if all(v is not None for v in (hq["pressure_allowed"], aq["pressure_allowed"], hs["def_pressure"], aws["def_pressure"])) else None,
            "qb_vs_blitz_matchup": hq["blitz_epa"] * aws["def_blitz"] - aq["blitz_epa"] * hs["def_blitz"] if all(v is not None for v in (hq["blitz_epa"], aq["blitz_epa"], hs["def_blitz"], aws["def_blitz"])) else None,
            "receiver_separation_diff": difference(hk["separation"], ak["separation"]), "receiver_yac_oe_diff": difference(hk["yac_oe"], ak["yac_oe"]),
            "rush_yoe_diff": difference(hk["rush_yoe"], ak["rush_yoe"]),
            "special_epa_diff": difference(hs["special_epa"], aws["special_epa"]), "starting_field_position_diff": difference(hs["start_yards"], aws["start_yards"]),
            "kicking_residual_diff": difference(kicking.get(home), kicking.get(away)),
            "travel_km_diff": difference(htravel["km"], atravel["km"]), "body_clock_shift_diff": difference(htravel["clock_shift"], atravel["clock_shift"]),
            "timezone_crossings_diff": difference(htravel["zones_crossed"], atravel["zones_crossed"]),
            "eastward_shift_diff": difference(htravel["eastward"], atravel["eastward"]),
            "westward_shift_diff": difference(htravel["westward"], atravel["westward"]),
            "early_home_clock_diff": difference(htravel["early_clock"], atravel["early_clock"]),
            "late_home_clock_diff": difference(htravel["late_clock"], atravel["late_clock"]),
            "rest_adjusted_shift_diff": difference(htravel["rest_adjusted_shift"], atravel["rest_adjusted_shift"]),
            "consecutive_road_diff": htravel["consecutive_road"] - atravel["consecutive_road"],
            "wind_depth_diff": wind / 15 * difference(hs["air_depth"], aws["air_depth"]) if outdoor and wind is not None and hs["air_depth"] is not None and aws["air_depth"] is not None else None if outdoor else 0.,
            "wind_kicking_diff": wind / 15 * difference(kicking.get(home), kicking.get(away)) if outdoor and wind is not None and kicking.get(home) is not None and kicking.get(away) is not None else None if outdoor else 0.,
            "wet_pass_diff": wet * passdiff if outdoor and wet is not None else None if outdoor else 0.,
        })
        for feature, off, defense in [("play_action_matchup", "play_action", "def_pa_epa"), ("motion_matchup", "motion", "def_motion_pass_epa"), ("screen_matchup", "screen", "def_screen_pass_epa")]:
            features[feature] = hs[off] * aws[defense] - aws[off] * hs[defense] if all(v is not None for v in (hs[off], aws[off], hs[defense], aws[defense])) else None
        features["deep_pass_matchup"] = hs["deep_epa"] + aws["def_deep_epa"] - aws["deep_epa"] - hs["def_deep_epa"] if all(v is not None for v in (hs["deep_epa"], aws["def_deep_epa"], hs["def_deep_epa"], aws["deep_epa"])) else None
        return features, {"home_qb": hq, "away_qb": aq, "home_injuries": hi, "away_injuries": ai,
                          "home_state": hs, "away_state": aws, "home_adjusted": hr, "away_adjusted": ar,
                          "home_skill": hk, "away_skill": ak, "home_travel": htravel, "away_travel": atravel,
                          "home_kicker": {"id": hkid, "residual": kicking.get(home)}, "away_kicker": {"id": akid, "residual": kicking.get(away)},
                          "weather": {"outdoor": outdoor, "temperature_f": temperature, "wind_mph": wind, "precip_probability": wet}}
