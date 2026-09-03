"""Synthetic payloads shaped like the federation API.

Invented clubs and invented people. No data collected from the federation is
committed to this repository; see docs/DATA_POLICY.en.md.
"""

SERIES = {
    "_id": "series-1",
    "year": "2099",
    "name": "Example League 2099 Division 1",
    "shortName": "1部リーグ",
    "type": "league",
    "requirements": "1部",
}


def _player(pid, name, position, number):
    return {"playerId": pid, "name": name, "position": position, "number": number}


TEAMS = [
    {
        "_id": "team-a",
        "seriesId": "series-1",
        "teamId": "100",
        "name": "Alpha University Football Club",
        "shortName": "Alpha",
        "members": [
            {
                "role": "player", "playerId": f"a{index}", "name": f"Alpha Player {index}",
                "kana": f"アルファ {index}", "number": str(index), "position": "MF",
                "class": "2", "height": "175", "weight": "68", "formerTeam": "Example High",
            }
            for index in range(1, 15)
        ],
        "rankingData": {
            "gameCount": 1, "win": 1, "lose": 0, "draw": 0, "point": 3,
            "goalDifferential": 2, "score": 2, "fairplayPoint": 0,
        },
    },
    {
        "_id": "team-b",
        "seriesId": "series-1",
        "teamId": "200",
        "name": "Beta University Football Club",
        "shortName": "Beta",
        "members": [
            {
                "role": "player", "playerId": f"b{index}", "name": f"Beta Player {index}",
                "kana": f"ベータ {index}", "number": str(index), "position": "DF",
                "class": "3", "height": "180", "weight": "72", "formerTeam": "Sample High",
            }
            for index in range(1, 15)
        ],
        "rankingData": {
            "gameCount": 1, "win": 0, "lose": 1, "draw": 0, "point": 0,
            "goalDifferential": -2, "score": 0, "fairplayPoint": 3,
        },
    },
]


def _record(record_id, team_id, prefix, score, *, shots, starters, subs, events):
    return {
        "_id": record_id,
        "team": {"_id": team_id, "display": prefix.title()},
        "score": str(score),
        "pk": "0",
        "point": "3" if score else "0",
        "goalDifferential": str(score - (2 - score)),
        "fairplayPoint": "0",
        "mcm": {"name": f"{prefix.title()} Manager", "post": "監督"},
        "starters": [
            {"value": _player(f"{prefix}{i}", f"{prefix.title()} Player {i}", "MF", str(i))}
            for i in starters
        ],
        "benches": [
            {"value": _player(f"{prefix}{i}", f"{prefix.title()} Player {i}", "FW", str(i))}
            for i in range(12, 15)
        ],
        "shoots": [
            {"value": {"playerId": f"{prefix}{pid}", "first": str(a), "second": str(b),
                       "third": "0", "fourth": "0"}}
            for pid, a, b in shots
        ],
        "substitutions": [
            {"value": {"outPlayerId": f"{prefix}{out}", "inPlayerId": f"{prefix}{into}",
                       "time": time}}
            for out, into, time in subs
        ],
        "records": [{"value": dict(event, playerId=f"{prefix}{event.pop('pid')}")}
                    for event in events],
        "suspensions": [],
    }


GAME = {
    "_id": "game-1",
    "seriesId": "series-1",
    "section": "1",
    "date": "2099-04-01 14:00:00",
    "venue": "Example Ground",
    "gameOver": True,
    "published": True,
    "matchTime": "90",
    "extraTime": "0",
    "gameRecords": [
        _record(
            "record-a", "team-a", "a", 2,
            shots=[(1, 2, 1), (2, 0, 3), (11, 1, 0)],
            starters=range(1, 12),
            subs=[(11, 12, "HT"), (2, 13, "70")],
            events=[
                {"pid": 1, "type": "goal", "time": "12"},
                {"pid": 12, "type": "goal", "time": "90+2"},
                {"pid": 3, "type": "card", "card": "C2", "time": "55"},
            ],
        ),
        _record(
            "record-b", "team-b", "b", 0,
            shots=[(4, 1, 1)],
            starters=range(1, 12),
            subs=[(4, 12, "80")],
            events=[{"pid": 5, "type": "card", "card": "S2", "time": "30"}],
        ),
    ],
}


#: A reverse fixture, so tests that need a table, a points curve or an
#: opponent split have more than one result to work with.
GAME2 = {
    "_id": "game-2",
    "seriesId": "series-1",
    "section": "2",
    "date": "2099-04-08 14:00:00",
    "venue": "Sample Park",
    "gameOver": True,
    "published": True,
    "matchTime": "90",
    "extraTime": "0",
    "gameRecords": [
        _record(
            "record-b2", "team-b", "b", 1,
            shots=[(1, 1, 2), (3, 0, 1)],
            starters=range(1, 12),
            subs=[(3, 12, "60")],
            events=[{"pid": 1, "type": "goal", "time": "20"}],
        ),
        _record(
            "record-a2", "team-a", "a", 0,
            shots=[(1, 1, 0), (5, 0, 1)],
            starters=range(1, 12),
            subs=[],
            events=[],
        ),
    ],
}


class FakeClient:
    """Stands in for :class:`togakuren.client.Client` in tests."""

    def series(self, year=None):
        return [SERIES]

    def teams(self, series_id):
        return TEAMS

    #: Number of fixtures this client serves.
    fixtures = 1

    def games(self, series_id):
        return [GAME] if self.fixtures == 1 else [GAME, GAME2]


class TwoGameClient(FakeClient):
    """Serves both fixtures, giving tests a league table to reason about."""

    fixtures = 2


def _scheduled(record_id, team_id, prefix):
    """A record for a fixture that has not been played: named sides, no score."""
    return {
        "_id": record_id,
        "team": {"_id": team_id, "display": prefix.title()},
        "score": "", "pk": "0", "point": "0", "goalDifferential": "0",
        "fairplayPoint": "0", "mcm": {"name": "", "post": ""},
        "starters": [], "benches": [], "shoots": [], "substitutions": [],
        "records": [], "suspensions": [],
    }


#: A fixture still to play, so the forecasting command has something to forecast.
GAME3 = {
    "_id": "game-3",
    "seriesId": "series-1",
    "section": "3",
    "date": "2099-04-15 14:00:00",
    "venue": "Example Ground",
    "gameOver": False,
    "published": True,
    "matchTime": "90",
    "extraTime": "0",
    "gameRecords": [
        _scheduled("record-a3", "team-a", "a"),
        _scheduled("record-b3", "team-b", "b"),
    ],
}


class UnfinishedSeasonClient(FakeClient):
    """Two results and one fixture still to come."""

    fixtures = 3

    def games(self, series_id):
        return [GAME, GAME2, GAME3]


def seed_seasons(conn):
    """Fill ``conn`` with three seasons of two invented divisions.

    The preseason model needs several seasons, a division wide enough to have a
    spread, standings, and a ``former_team`` on every squad row, so the
    single-season fixture above cannot exercise it. Half of each club's players
    come from a school that really does appear in the championship reference, so
    the pedigree column has something to find; nobody here is a real person.
    """
    for year in ("2001", "2002", "2003"):
        for tier, division in ((1, "1部リーグ"), (2, "2部リーグ")):
            series_id = f"s{year}-{tier}"
            conn.execute(
                "INSERT INTO series (id, year, name, short_name, type, division) "
                "VALUES (?, ?, ?, ?, 'league', ?)",
                (series_id, year, f"Example {year} {division}", division, division),
            )
            for index in range(6):
                team_pk = f"{series_id}-t{index}"
                club = f"club-{tier}{index}"
                conn.execute(
                    "INSERT INTO teams (id, series_id, team_id, name, short_name) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (team_pk, series_id, club, f"Club {club}", f"Club {club}"),
                )
                conn.execute(
                    "INSERT INTO standings (team_pk, series_id, played, win, draw, lose, "
                    "points, goals_for, goal_difference, fairplay_points) "
                    "VALUES (?, ?, 10, ?, 0, ?, ?, 10, 0, 0)",
                    (team_pk, series_id, index, 10 - index, index * 3),
                )
                # A fixture makes the season count as "player data recorded".
                game_id = f"{team_pk}-g"
                conn.execute(
                    "INSERT INTO games (id, series_id, section, name, kickoff, venue, "
                    "game_over, length) VALUES (?, ?, '1', 'g', '', '', 1, 90)",
                    (game_id, series_id),
                )
                conn.execute(
                    "INSERT INTO game_teams (id, game_id, series_id, team_pk, score, "
                    "points, goal_difference, fairplay_points) "
                    "VALUES (?, ?, ?, ?, 1, 3, 0, 0)",
                    (f"{team_pk}-gt", game_id, series_id, team_pk),
                )
                for player in range(12):
                    player_id = f"{team_pk}-p{player}"
                    conn.execute(
                        "INSERT INTO players (player_id, name, kana) VALUES (?, ?, '')",
                        (player_id, f"Player {player}"),
                    )
                    strong = player < index * 2
                    conn.execute(
                        "INSERT INTO squad_members (series_id, team_pk, player_id, number, "
                        "position, grade, former_team) VALUES (?, ?, ?, ?, 'MF', ?, ?)",
                        (series_id, team_pk, player_id, str(player + 1),
                         str(player % 4 + 1),
                         "青森山田高校" if strong else "架空第一高校"),
                    )
                    conn.execute(
                        "INSERT INTO appearances (game_team_id, player_id, role, position, "
                        "number, minutes) VALUES (?, ?, 'start', 'MF', ?, 90)",
                        (f"{team_pk}-gt", player_id, str(player + 1)),
                    )
    conn.commit()
    return conn
