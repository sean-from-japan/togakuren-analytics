"""Normalisation of raw API payloads into flat rows.

Everything here is a pure function over plain dictionaries, so the whole
normalisation layer — including the minutes reconstruction, which is the only
genuinely non-obvious step — is testable without touching the network.
"""

import re
import unicodedata

DEFAULT_MATCH_LENGTH = 90

RED_CARDS = frozenset({"S1", "S2", "S3", "S4", "S5", "S6", "CS"})

#: Shot counts are stored under four keys. The federation documents none of
#: them, but across the 2022-2026 seasons ``third`` is non-zero only in knockout
#: competitions that went to extra time and ``fourth`` is never used at all, so
#: they are the two halves followed by the two extra-time halves.
SHOT_PERIODS = ("first", "second", "third", "fourth")

#: Human-readable names for :data:`SHOT_PERIODS`, in the same order.
SHOT_PERIOD_NAMES = ("first_half", "second_half", "extra_first", "extra_second")

_STOPPAGE = re.compile(r"^(\d+)\s*\+\s*(\d+)$")


def parse_minute(value, half_time=DEFAULT_MATCH_LENGTH // 2):
    """Parse an event minute as recorded by the federation.

    The field is free text entered by match officials and appears in the data as
    a plain number (``"58"``), the half-time marker (``"HT"``), or stoppage time
    written either with an ASCII plus (``"90+2"``) or a superscript one
    (``"90⁺5"``). Returns ``None`` for anything unparseable.
    """
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    if not text:
        return None
    if text.upper() == "HT":
        return half_time

    stoppage = _STOPPAGE.match(text)
    if stoppage:
        return int(stoppage.group(1)) + int(stoppage.group(2))
    try:
        return int(text)
    except ValueError:
        return None


def match_length(game):
    """Regulation length of one fixture, in minutes."""
    base = game.get("matchTime")
    try:
        base = int(base)
    except (TypeError, ValueError):
        base = DEFAULT_MATCH_LENGTH
    try:
        extra = int(game.get("extraTime") or 0)
    except (TypeError, ValueError):
        extra = 0
    return base + extra


def _values(record, key):
    """Cockpit stores repeaters as ``[{"value": {...}}, ...]``."""
    return [item["value"] for item in (record.get(key) or []) if isinstance(item, dict) and "value" in item]


def appearances(record, length=DEFAULT_MATCH_LENGTH):
    """Reconstruct who was on the pitch, and for how long.

    The federation records a starting eleven, a bench, and timed substitutions,
    but never minutes played. This walks those three lists into one row per
    player.

    A player sent off leaves the pitch at the minute of the red card, which the
    substitution list does not capture — without this the dismissed player would
    be credited with the full match.

    Args:
        record: one entry of a fixture's ``gameRecords``.
        length: regulation length of the fixture, from :func:`match_length`.

    Returns:
        A list of dicts with ``player_id``, ``role``, ``position``, ``number``,
        ``on``, ``off`` and ``minutes``.
    """
    half = length // 2
    starters = _values(record, "starters")
    bench = _values(record, "benches")

    meta = {}
    for player in starters:
        meta[player["playerId"]] = ("start", player)
    for player in bench:
        meta.setdefault(player["playerId"], ("bench", player))

    on = {player["playerId"]: 0 for player in starters}
    off = {}

    for sub in _values(record, "substitutions"):
        minute = parse_minute(sub.get("time"), half)
        if minute is None:
            continue
        out_id, in_id = sub.get("outPlayerId"), sub.get("inPlayerId")
        if out_id and out_id in on and out_id not in off:
            off[out_id] = minute
        if in_id and in_id not in on:
            on[in_id] = minute

    for event in _values(record, "records"):
        if event.get("type") != "card" or event.get("card") not in RED_CARDS:
            continue
        minute = parse_minute(event.get("time"), half)
        player_id = event.get("playerId")
        if minute is not None and player_id in on:
            off[player_id] = min(off.get(player_id, length), minute)

    rows = []
    for player_id, entered in on.items():
        role, player = meta.get(player_id, ("bench", {}))
        left = min(off.get(player_id, length), length)
        rows.append(
            {
                "player_id": player_id,
                "role": role,
                "position": player.get("position"),
                "number": player.get("number"),
                "on": entered,
                "off": left,
                "minutes": max(0, left - entered),
            }
        )
    rows.sort(key=lambda row: (row["role"] != "start", -row["minutes"]))
    return rows


def shots(record):
    """One row per player with a shot line, split by period and totalled."""
    rows = []
    for shot in _values(record, "shoots"):
        counts = []
        for period in SHOT_PERIODS:
            try:
                counts.append(int(shot.get(period) or 0))
            except (TypeError, ValueError):
                counts.append(0)
        rows.append(
            {
                "player_id": shot.get("playerId"),
                "periods": counts,
                "total": sum(counts),
            }
        )
    return rows


def events(record, length=DEFAULT_MATCH_LENGTH):
    """Goals and cards, flattened to ``type``/``code``/``minute`` rows."""
    half = length // 2
    rows = []
    for event in _values(record, "records"):
        kind = event.get("type")
        if kind not in ("goal", "card"):
            continue
        code = event.get("card")
        rows.append(
            {
                "player_id": event.get("playerId"),
                "type": "red" if code in RED_CARDS else ("yellow" if kind == "card" else "goal"),
                "code": code,
                "minute": parse_minute(event.get("time"), half),
            }
        )
    return rows


def substitutions(record, length=DEFAULT_MATCH_LENGTH):
    half = length // 2
    return [
        {
            "out_player_id": sub.get("outPlayerId"),
            "in_player_id": sub.get("inPlayerId"),
            "minute": parse_minute(sub.get("time"), half),
        }
        for sub in _values(record, "substitutions")
    ]


def roster(team):
    """Squad members of one ``seriesTeams`` entry."""
    rows = []
    for member in team.get("members") or []:
        if member.get("role") and member.get("role") != "player":
            continue
        player_id = member.get("playerId")
        if not player_id:
            continue
        rows.append(
            {
                "player_id": player_id,
                "name": member.get("name"),
                "kana": member.get("kana"),
                "number": member.get("number"),
                "position": member.get("position"),
                "grade": member.get("class"),
                "height": member.get("height"),
                "weight": member.get("weight"),
                "former_team": member.get("formerTeam"),
            }
        )
    return rows


def standings(team):
    """The league table row the CMS keeps alongside each squad."""
    data = team.get("rankingData") or {}
    if not data:
        return None
    return {
        "played": data.get("gameCount"),
        "win": data.get("win"),
        "draw": data.get("draw"),
        "lose": data.get("lose"),
        "points": data.get("point"),
        "goals_for": data.get("score"),
        "goal_difference": data.get("goalDifferential"),
        "fairplay_points": data.get("fairplayPoint"),
    }
