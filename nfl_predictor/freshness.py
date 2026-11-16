"""Pregame checks. Retrieval time alone never establishes an official lineup."""

from datetime import datetime, timezone
import math

UTC = timezone.utc
REQUIRED = {"stats": 48., "injuries": 24., "depth": 24., "weather": 12., "staff": 168.}


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamps must include a timezone")
    return result.astimezone(UTC)


def check_pregame(game, now=None, final=False):
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Current time must include a timezone")
    kickoff = timestamp(game["kickoff"])
    reasons = []
    if kickoff <= now or game.get("state") != "pre":
        reasons.append("Game has started, finished, or is not confirmed pregame")
    if final and (kickoff - now).total_seconds() > 2 * 3600:
        reasons.append("Final check must be within two hours before kickoff")
    requirements = dict(REQUIRED)
    if final:
        requirements.update(injuries=2., depth=2., weather=6., inactives=2.)
    for kind, max_hours in requirements.items():
        source = game.get("sources", {}).get(kind)
        if not source or source.get("status") != "ok" or not source.get("url"):
            reasons.append(f"{kind}: missing or unsuccessful source")
            continue
        if str(source.get("event_id")) != str(game["event_id"]):
            reasons.append(f"{kind}: source is for a different game")
        try:
            retrieved = timestamp(source["retrieved_at"])
            age = (now - retrieved).total_seconds() / 3600
            if age < 0 or age > max_hours:
                reasons.append(f"{kind}: future-dated or older than {max_hours:g} hours")
        except (KeyError, ValueError, TypeError):
            reasons.append(f"{kind}: invalid retrieval timestamp")
        if kind == "stats" and (source.get("season") != game.get("season") or
                                source.get("through_week") != int(game["week"]) - 1):
            reasons.append("stats: require this season through exactly the previous week")
        if kind == "weather":
            # An explicitly verified enclosed venue does not need outdoor weather.
            if source.get("enclosed_verified") is not True:
                try:
                    valid = timestamp(source["valid_at"])
                    if abs((valid - kickoff).total_seconds()) > 3600:
                        reasons.append("weather: conditions are not near kickoff")
                    for metric in ("temperature_f", "wind_mph"):
                        value = source.get(metric)
                        if not isinstance(value, (int, float)) or not math.isfinite(value):
                            reasons.append(f"weather: missing {metric}")
                    if isinstance(source.get("wind_mph"), (int, float)) and source["wind_mph"] < 0:
                        reasons.append("weather: negative wind speed")
                except (KeyError, ValueError, TypeError):
                    reasons.append("weather: missing or invalid forecast valid time")
        if kind == "inactives":
            verified = source.get("verified_teams", [])
            if source.get("official") is not True or set(verified) != {game["home"], game["away"]}:
                reasons.append("inactives: official lists for both teams are not verified")
    return {"event_id": str(game["event_id"]), "checked_at": now.isoformat(),
            "stage": "final" if final else "preliminary", "ready": not reasons,
            "reasons": reasons}
