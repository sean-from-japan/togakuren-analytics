"""Synthetic payloads shaped like the federation API.

Invented clubs and invented people. No data collected from the federation is
committed to this repository; see docs/DATA_POLICY.md.
"""

SERIES = {
    "_id": "series-1",
    "year": "2099",
    "name": "Example League 2099 Division 1",
    "shortName": "D1",
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


class FakeClient:
    """Stands in for :class:`togakuren.client.Client` in tests."""

    def series(self, year=None):
        return [SERIES]

    def teams(self, series_id):
        return TEAMS

    def games(self, series_id):
        return [GAME]
