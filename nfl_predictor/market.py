"""Independent, timestamp-aligned market benchmarks; never target leakage."""
from datetime import datetime, timezone
import csv
import json
import math
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .freshness import timestamp


def implied_probability(american):
    value = float(str(american).replace("−", "-").replace("EVEN", "100"))
    if not math.isfinite(value) or abs(value) < 100:
        raise ValueError("Invalid American odds")
    return 100 / (value + 100) if value > 0 else -value / (-value + 100)


def remove_margin(home_price, away_price):
    home, away = implied_probability(home_price), implied_probability(away_price)
    return {"home_probability": home / (home + away), "overround": home + away - 1}


def espn_quotes(summary, game, receipt):
    observed = receipt["retrieved_at"]
    if timestamp(observed) >= timestamp(game["kickoff"]):
        return []
    quotes = []
    for center in summary.get("pickcenter", []):
        try:
            ml = center.get("moneyline", {})
            home = center.get("homeTeamOdds", {}).get("moneyLine")
            away = center.get("awayTeamOdds", {}).get("moneyLine")
            if home is None:
                home = ml["home"]["close"]["odds"]
            if away is None:
                away = ml["away"]["close"]["odds"]
            quotes.append({"event_id": game["event_id"], "book": center.get("provider", {}).get("name", "ESPN-listed provider"),
                           "home_price": float(home), "away_price": float(away), **remove_margin(home, away),
                           "observed_at": observed, "url": receipt["url"],
                           "timing": "Latest quote observed before kickoff; provider update time not independently established"})
        except (KeyError, ValueError, TypeError):
            continue
    return quotes


def aligned_consensus(quotes, issued_at, kickoff, max_age_minutes=10):
    latest = {}
    for quote in quotes:
        observed = timestamp(quote["observed_at"])
        age = (timestamp(issued_at) - observed).total_seconds()
        if 0 <= age <= max_age_minutes * 60 and observed < timestamp(kickoff):
            # Recompute from a single book's paired prices, never mix opposite sides.
            item = {**quote, **remove_margin(quote["home_price"], quote["away_price"])}
            if quote["book"] not in latest or observed > timestamp(latest[quote["book"]]["observed_at"]):
                latest[quote["book"]] = item
    valid = list(latest.values())
    if not valid:
        return {"status": "unavailable", "reason": "No paired quote observed within ten minutes before issue", "quotes": []}
    probabilities = sorted(q["home_probability"] for q in valid)
    mid = len(probabilities) // 2
    median = probabilities[mid] if len(probabilities) % 2 else (probabilities[mid - 1] + probabilities[mid]) / 2
    return {"status": "ok", "home_probability": median, "books": len({q["book"] for q in valid}),
            "method": "Median of same-book two-way probabilities after proportional margin removal", "quotes": valid}


def csv_quotes(path):
    """Import paired, timestamped observations; alignment is enforced at issue."""
    with open(path, encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        if any(not row.get(key) for key in ("event_id", "book", "home_price", "away_price", "observed_at", "url")):
            raise ValueError("Market CSV requires event_id, book, home_price, away_price, observed_at, url")
        timestamp(row["observed_at"])
        row.update(remove_margin(row["home_price"], row["away_price"]))
    return rows


def odds_api_quotes():
    """Opt-in adapter; the key is sent in a header and never returned or stored."""
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        raise ValueError("Set ODDS_API_KEY in your local environment; do not put it in a file or chat")
    url = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds?" + urlencode({"regions": "us", "markets": "h2h", "oddsFormat": "american"})
    with urlopen(Request(url, headers={"x-api-key": key, "User-Agent": "NoFunLeaguePredictor/4.0"}), timeout=30) as response:
        payload = json.load(response)
    return {"observed_at": datetime.now(timezone.utc).isoformat(), "url": url, "events": payload}


def elo_probability(dataset, game, home_advantage=55., k=20.):
    ratings, current_season = {}, None
    rows = sorted(dataset["schedule"], key=lambda g: (g["season"], g["week"], g["gameday"], g["gametime"] or "", g["game_id"]))
    for row in rows:
        if (row["season"], row["week"]) >= (game["season"], game["week"]):
            break
        if current_season != row["season"]:
            ratings = {team: 1500 + .67 * (rating - 1500) for team, rating in ratings.items()}
            current_season = row["season"]
        if row.get("home_score") is None:
            continue
        home, away = row["home_team"], row["away_team"]
        rh, ra = ratings.get(home, 1500.), ratings.get(away, 1500.)
        advantage = 0. if row.get("location") == "Neutral" else home_advantage
        p = 1 / (1 + 10 ** ((ra - rh - advantage) / 400))
        result = .5 if row["home_score"] == row["away_score"] else float(row["home_score"] > row["away_score"])
        delta = k * (result - p)
        ratings[home], ratings[away] = rh + delta, ra - delta
    if current_season != game["season"]:
        ratings = {team: 1500 + .67 * (rating - 1500) for team, rating in ratings.items()}
    advantage = 0. if game.get("location") == "Neutral" else home_advantage
    return 1 / (1 + 10 ** ((ratings.get(game["away_team"], 1500.) - ratings.get(game["home_team"], 1500.) - advantage) / 400))
