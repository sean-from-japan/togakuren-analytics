"""A synthetic season, for showing player-level output without a real person in it.

The player-level views are the interesting half of this tool and the half that
can never be published from real records. Rather than redact a screenshot, this
generates a fictional league in the shape of the federation's own payloads and
runs it through the ordinary ingest, so the documented output is produced by the
same code path as the real thing.

Every club, player and result here is invented. Any resemblance is coincidence.
"""

import random

from . import ingest

CLUBS = [
    ("Aoi Institute of Technology", "Aoi"),
    ("Hikari University", "Hikari"),
    ("Kaede College", "Kaede"),
    ("Minato University", "Minato"),
    ("Nagi University of Science", "Nagi"),
    ("Sakura Gakuin University", "Sakura"),
    ("Tsubasa University", "Tsubasa"),
    ("Yuki Metropolitan University", "Yuki"),
]

FAMILY = ["Aoki", "Endo", "Fujita", "Goto", "Hayashi", "Inoue", "Kato", "Kimura",
          "Maeda", "Nakano", "Ono", "Saito", "Takeda", "Ueda", "Wada", "Yamashita"]
GIVEN = ["Daiki", "Haruto", "Kenji", "Naoki", "Ren", "Riku", "Shota", "Sora",
         "Takumi", "Yuma", "Yuto", "Kaito", "Hiroto", "Souta", "Asahi", "Itsuki"]

FORMATION = ["GK"] + ["DF"] * 4 + ["MF"] * 4 + ["FW"] * 2
SQUAD_SIZE = 20
ROUNDS = 14


def _squad(rng, club_index):
    """Twenty invented players with positions, shirt numbers and year groups."""
    members = []
    for index in range(SQUAD_SIZE):
        position = FORMATION[index] if index < len(FORMATION) else rng.choice(FORMATION[1:])
        members.append(
            {
                "role": "player",
                "playerId": f"{club_index:02d}{index:03d}",
                "name": f"{rng.choice(FAMILY)} {rng.choice(GIVEN)}",
                "kana": "",
                "number": str(index + 1),
                "position": position,
                "class": str(rng.choices([1, 2, 3, 4], weights=[3, 4, 5, 5])[0]),
                "birthday": "",
                "height": str(rng.randint(165, 186)),
                "weight": str(rng.randint(58, 80)),
                "formerTeam": "",
            }
        )
    return members


def _record(rng, record_id, team_pk, squad, strength, goals):
    """One team's half of a fixture: eleven, bench, shots, changes, cards."""
    keepers = [p for p in squad if p["position"] == "GK"]
    outfield = [p for p in squad if p["position"] != "GK"]
    # A settled core plus a rotating fringe, so minutes are not uniform.
    core = outfield[: 7 + rng.randint(0, 4)]
    rest = [p for p in outfield if p not in core]
    rng.shuffle(rest)
    starters = [keepers[0]] + core[:10] if len(core) >= 10 else [keepers[0]] + core + rest[: 10 - len(core)]
    starters = starters[:11]
    bench = [p for p in squad if p not in starters][:7]

    def player_entry(player):
        return {"value": {"playerId": player["playerId"], "position": player["position"],
                          "number": player["number"], "name": player["name"]}}

    substitutions, used = [], []
    for _ in range(rng.randint(1, 5)):
        candidates = [p for p in starters[1:] if p not in used]
        incoming = [p for p in bench if p["position"] != "GK" and p not in used]
        if not candidates or not incoming:
            break
        out_player, in_player = rng.choice(candidates), rng.choice(incoming)
        used += [out_player, in_player]
        substitutions.append(
            {"value": {"outPlayerId": out_player["playerId"],
                       "inPlayerId": in_player["playerId"],
                       "time": rng.choice(["HT", str(rng.randint(55, 88)), "90+1"])}}
        )

    on_pitch = starters + [p for p in used if p in bench]
    shots = []
    for player in on_pitch:
        weight = {"GK": 0, "DF": 1, "MF": 3, "FW": 5}[player["position"]]
        first = rng.choices([0, 1, 2, 3], weights=[16, weight + 2, max(weight - 2, 0), 1])[0]
        second = rng.choices([0, 1, 2, 3], weights=[16, weight + 2, max(weight - 2, 0), 1])[0]
        shots.append({"value": {"playerId": player["playerId"], "first": str(first),
                                "second": str(second), "third": "0", "fourth": "0"}})

    scorers = [p for p in on_pitch if p["position"] in ("MF", "FW")] or on_pitch
    records = []
    for _ in range(goals):
        records.append({"value": {"playerId": rng.choice(scorers)["playerId"],
                                  "type": "goal", "time": str(rng.randint(3, 92))}})
    for _ in range(rng.choices([0, 1, 2], weights=[5, 4, 1])[0]):
        records.append({"value": {"playerId": rng.choice(on_pitch)["playerId"], "type": "card",
                                  "card": rng.choice(["C1", "C2", "C3"]), "time": str(rng.randint(20, 90))}})
    if rng.random() < 0.04:
        records.append({"value": {"playerId": rng.choice(starters[1:])["playerId"], "type": "card",
                                  "card": "S2", "time": str(rng.randint(30, 80))}})

    return {
        "_id": record_id,
        "team": {"_id": team_pk, "display": None},
        "score": str(goals), "pk": "0",
        "point": None, "goalDifferential": "0", "fairplayPoint": "0",
        "mcm": {"name": "", "post": "監督"},
        "starters": [player_entry(p) for p in starters],
        "benches": [player_entry(p) for p in bench],
        "shoots": shots,
        "substitutions": substitutions,
        "records": records,
        "suspensions": [],
    }


class SampleClient:
    """Stands in for :class:`togakuren.client.Client`, serving invented records."""

    def __init__(self, seed=20260829, year="2099"):
        self.rng = random.Random(seed)
        self.year = year
        self.strength = {index: self.rng.uniform(0.7, 1.9) for index in range(len(CLUBS))}
        self.squads = {index: _squad(self.rng, index) for index in range(len(CLUBS))}
        self._games = None

    def series(self, year=None):
        return [
            {
                "_id": "sample-series",
                "year": self.year,
                "name": f"Example University Football League {self.year} — Division 1",
                "shortName": "1部リーグ",
                "type": "league",
                "requirements": "1部",
            }
        ]

    def teams(self, series_id):
        return [
            {
                "_id": f"sample-team-{index}",
                "seriesId": series_id,
                "teamId": f"90{index}",
                "name": name,
                "shortName": short,
                "members": self.squads[index],
                "rankingData": self._table()[index],
            }
            for index, (name, short) in enumerate(CLUBS)
        ]

    def games(self, series_id):
        if self._games is None:
            self._build(series_id)
        return self._games

    def _build(self, series_id):
        rng = self.rng
        # Key names mirror the federation's own rankingData payload so the
        # ordinary normalisation reads it without a special case.
        games, table = [], {i: {"win": 0, "draw": 0, "lose": 0, "point": 0, "score": 0,
                                "against": 0, "gameCount": 0} for i in range(len(CLUBS))}
        order = list(range(len(CLUBS)))
        for section in range(1, ROUNDS + 1):
            rng.shuffle(order)
            for pair in range(0, len(order) - 1, 2):
                home, away = order[pair], order[pair + 1]
                home_goals = rng.choices([0, 1, 2, 3, 4], weights=[4, 6, 5, 3, 1])[0]
                away_goals = rng.choices([0, 1, 2, 3, 4], weights=[4, 6, 5, 3, 1])[0]
                home_goals = min(6, int(home_goals * self.strength[home] / self.strength[away] + 0.3))
                away_goals = min(6, int(away_goals * self.strength[away] / self.strength[home] + 0.3))
                game_id = f"sample-game-{section}-{pair}"
                games.append(
                    {
                        "_id": game_id, "seriesId": series_id, "section": str(section),
                        "date": f"{self.year}-04-{(section % 28) + 1:02d} 14:00:00",
                        "venue": "Example Ground", "gameOver": True, "published": True,
                        "matchTime": "90", "extraTime": "0",
                        "gameRecords": [
                            _record(rng, f"{game_id}-h", f"sample-team-{home}",
                                    self.squads[home], self.strength[home], home_goals),
                            _record(rng, f"{game_id}-a", f"sample-team-{away}",
                                    self.squads[away], self.strength[away], away_goals),
                        ],
                    }
                )
                for side, own, other in ((home, home_goals, away_goals), (away, away_goals, home_goals)):
                    entry = table[side]
                    entry["gameCount"] += 1
                    entry["score"] += own
                    entry["against"] += other
                    if own > other:
                        entry["win"] += 1
                        entry["point"] += 3
                    elif own == other:
                        entry["draw"] += 1
                        entry["point"] += 1
                    else:
                        entry["lose"] += 1
        for index, entry in table.items():
            entry["goalDifferential"] = entry["score"] - entry["against"]
            entry["fairplayPoint"] = 0
        self._games = games
        self._table_data = table

    def _table(self):
        if self._games is None:
            self._build("sample-series")
        return self._table_data


def generate(conn, seed=20260829, year="2099"):
    """Populate ``conn`` with one synthetic season. Returns the series id."""
    client = SampleClient(seed=seed, year=year)
    series = client.series()[0]
    ingest.ingest_series(conn, client, series)
    # Per-match points are not part of the federation's payload for this shape,
    # so derive them from the scorelines the generator already produced.
    conn.execute(
        """
        UPDATE game_teams SET points = (
            SELECT CASE WHEN game_teams.score > opp.score THEN 3
                        WHEN game_teams.score = opp.score THEN 1 ELSE 0 END
            FROM game_teams opp
            WHERE opp.game_id = game_teams.game_id AND opp.id <> game_teams.id
        ) WHERE series_id = ?
        """,
        (series["_id"],),
    )
    conn.commit()
    return series["_id"]
