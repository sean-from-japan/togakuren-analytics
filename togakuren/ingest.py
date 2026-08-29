"""Fetch one or more series and load them into SQLite."""

import logging

from . import model
from .db import upsert

log = logging.getLogger(__name__)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def ingest_series(conn, client, series):
    """Load a single series (fixtures, squads, standings) into ``conn``."""
    series_id = series["_id"]
    upsert(
        conn,
        "series",
        [
            {
                "id": series_id,
                "year": series.get("year"),
                "name": series.get("name"),
                "short_name": series.get("shortName"),
                "type": series.get("type"),
                "division": series.get("requirements"),
            }
        ],
        ["id", "year", "name", "short_name", "type", "division"],
    )

    team_rows, standing_rows, player_rows, member_rows = [], [], [], []
    for team in client.teams(series_id):
        team_rows.append(
            {
                "id": team["_id"],
                "series_id": series_id,
                "team_id": team.get("teamId"),
                "name": team.get("name"),
                "short_name": team.get("shortName"),
            }
        )
        table = model.standings(team)
        if table:
            table.update({"team_pk": team["_id"], "series_id": series_id})
            standing_rows.append(table)
        for member in model.roster(team):
            player_rows.append(
                {"player_id": member["player_id"], "name": member["name"], "kana": member["kana"]}
            )
            member_rows.append(dict(member, series_id=series_id, team_pk=team["_id"]))

    upsert(conn, "teams", team_rows, ["id", "series_id", "team_id", "name", "short_name"])
    upsert(
        conn,
        "standings",
        standing_rows,
        [
            "team_pk", "series_id", "played", "win", "draw", "lose",
            "points", "goals_for", "goal_difference", "fairplay_points",
        ],
    )
    upsert(conn, "players", player_rows, ["player_id", "name", "kana"])
    upsert(
        conn,
        "squad_members",
        member_rows,
        [
            "series_id", "team_pk", "player_id", "number", "position",
            "grade", "height", "weight", "former_team",
        ],
    )

    games = client.games(series_id)
    game_rows, record_rows = [], []
    appearance_rows, shot_rows, event_rows, sub_rows = [], [], [], []

    for game in games:
        length = model.match_length(game)
        game_rows.append(
            {
                "id": game["_id"],
                "series_id": series_id,
                "section": game.get("section"),
                "name": game.get("name"),
                "kickoff": game.get("actualDate") or game.get("date"),
                "venue": None if game.get("hideVenue") else game.get("venue"),
                "game_over": 1 if game.get("gameOver") else 0,
                "length": length,
            }
        )

        for record in game.get("gameRecords") or []:
            record_id = record["_id"]
            manager = (record.get("mcm") or {}).get("name")
            record_rows.append(
                {
                    "id": record_id,
                    "game_id": game["_id"],
                    "series_id": series_id,
                    "team_pk": (record.get("team") or {}).get("_id"),
                    "score": _int(record.get("score")),
                    "penalties": _int(record.get("pk")),
                    "points": _int(record.get("point")),
                    "goal_difference": _int(record.get("goalDifferential")),
                    "fairplay_points": _int(record.get("fairplayPoint")),
                    "manager": manager,
                }
            )

            for row in model.appearances(record, length):
                appearance_rows.append(
                    {
                        "game_team_id": record_id,
                        "player_id": row["player_id"],
                        "role": row["role"],
                        "position": row["position"],
                        "number": row["number"],
                        "on_minute": row["on"],
                        "off_minute": row["off"],
                        "minutes": row["minutes"],
                    }
                )
            for row in model.shots(record):
                if not row["player_id"]:
                    continue
                shot_rows.append(
                    {
                        "game_team_id": record_id,
                        "player_id": row["player_id"],
                        "first_half": row["periods"][0],
                        "second_half": row["periods"][1],
                        "extra_first": row["periods"][2],
                        "extra_second": row["periods"][3],
                        "total": row["total"],
                    }
                )
            for seq, row in enumerate(model.events(record, length)):
                event_rows.append(dict(row, game_team_id=record_id, seq=seq))
            for seq, row in enumerate(model.substitutions(record, length)):
                sub_rows.append(dict(row, game_team_id=record_id, seq=seq))

    upsert(
        conn, "games", game_rows,
        ["id", "series_id", "section", "name", "kickoff", "venue", "game_over", "length"],
    )
    upsert(
        conn, "game_teams", record_rows,
        [
            "id", "game_id", "series_id", "team_pk", "score", "penalties",
            "points", "goal_difference", "fairplay_points", "manager",
        ],
    )
    upsert(
        conn, "appearances", appearance_rows,
        ["game_team_id", "player_id", "role", "position", "number",
         "on_minute", "off_minute", "minutes"],
    )
    upsert(
        conn, "shots", shot_rows,
        ["game_team_id", "player_id", "first_half", "second_half",
         "extra_first", "extra_second", "total"],
    )
    upsert(conn, "events", event_rows, ["game_team_id", "player_id", "type", "code", "minute", "seq"])
    upsert(
        conn, "substitutions", sub_rows,
        ["game_team_id", "seq", "out_player_id", "in_player_id", "minute"],
    )
    conn.commit()

    log.info("%s %s: %d games", series.get("year"), series.get("shortName"), len(games))
    return len(games)


def ingest_all(conn, client, years=None):
    """Load every series, optionally restricted to ``years``.

    A backfill spans dozens of requests, so one series failing must not throw
    away the rest. Failures are collected and reported at the end; re-running
    picks up where it stopped, because every series is loaded independently and
    cached responses cost nothing.
    """
    total, failures = 0, []
    for series in client.series():
        if years and series.get("year") not in {str(year) for year in years}:
            continue
        try:
            total += ingest_series(conn, client, series)
        except Exception as exc:  # noqa: BLE001 - one bad series must not stop the rest
            conn.rollback()
            label = f"{series.get('year')} {series.get('shortName') or series['_id']}"
            log.warning("skipped %s: %s: %s", label, type(exc).__name__, exc)
            failures.append(label)
    if failures:
        log.warning("\n%d series failed and were skipped: %s", len(failures), ", ".join(failures))
    return total
