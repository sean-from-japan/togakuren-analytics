"""Regularized adjusted plus-minus ratings.

The method is Sæbø and Hvattum's. A match is cut into segments at kick-off, at
every substitution and at every dismissal, so the twenty-two players on the pitch
are fixed inside a segment. The response is the goal difference scored inside the
segment; each player present enters as +1 for their own side and -1 for the other,
scaled by the segment's share of a full match. Ridge shrinkage keeps a player who
appeared for twenty minutes from being credited with the twenty minutes' noise.

Two details are worth stating because getting either wrong reverses the result:

* Club terms and player terms need **separate penalties**. Fifty-odd clubs need
  almost no shrinkage and two thousand players need a lot; one shared penalty
  over-shrinks the clubs and the joint model then scores worse than clubs alone.
* Goal events reconcile with the recorded score in only about four fifths of
  fixtures, because unattributed and own goals are stored as a count rather than
  as an event. A segment model cannot place those goals in time, so by default
  the fixtures that do not reconcile are left out rather than silently mis-scored.

The normal equations are solved by conjugate gradient over the sparse rows, which
keeps this module on the standard library and takes a few seconds over five
seasons. Forming the matrix itself would be thousands of columns squared.

Ratings are per player. They stay on the machine that produced them, like every
other player-level output here — see ``docs/DATA_POLICY.md``.
"""
import collections
import math
import random

from . import predict

#: Column scale for a segment that lasts a whole match.
FULL_MATCH = 90.0

#: Ridge penalty on player columns, and on club columns when they are included.
#: Chosen by grouped cross-validation over 2022-2026 league fixtures.
PLAYER_PENALTY = 30.0
CLUB_PENALTY = 0.1

#: Players below this many minutes in the fitting sample get no column of their
#: own; they are absorbed into the intercept-free baseline.
MIN_MINUTES = 270

Segment = collections.namedtuple(
    "Segment", "game year series clubs home minutes difference first second")


SIDES = "SELECT game_id, rowid FROM game_teams ORDER BY game_id, rowid"

SPELLS = """
SELECT gt.game_id AS game_id, gt.rowid AS side, a.player_id AS player,
       a.on_minute AS on_minute, a.off_minute AS off_minute
FROM appearances a
JOIN game_teams gt ON gt.id = a.game_team_id
"""

GOAL_MINUTES = """
SELECT gt.game_id AS game_id, gt.rowid AS side, e.minute AS minute
FROM events e
JOIN game_teams gt ON gt.id = e.game_team_id
WHERE e.type = 'goal'
"""


def _side_index(conn):
    """``{game_id: {game_team rowid: 0 or 1}}`` in the order :mod:`predict` uses."""
    grouped = collections.defaultdict(list)
    for game_id, rowid in conn.execute(SIDES):
        grouped[game_id].append(rowid)
    return {game: {rowid: index for index, rowid in enumerate(rowids)}
            for game, rowids in grouped.items()}


def segments(conn, matches=None, min_year=None, league_only=True, reconcile=True):
    """Every interval of unchanged lineups, as :class:`Segment` rows.

    ``reconcile`` drops fixtures whose timed goal events do not add up to the
    recorded score. Set it False only to measure how many there are.
    """
    matches = predict.load(conn) if matches is None else matches
    wanted = {}
    for match in matches:
        if not match["played"]:
            continue
        if league_only and match["type"] != "league":
            continue
        if min_year and match["year"] < min_year:
            continue
        if match["goals"][0] is None:
            continue
        wanted[match["game_id"]] = match

    sides = _side_index(conn)
    lengths = {row[0]: row[1] or 90 for row in conn.execute("SELECT id, length FROM games")}

    spells = collections.defaultdict(lambda: ([], []))
    for row in conn.execute(SPELLS):
        game = row["game_id"]
        if game not in wanted:
            continue
        on, off = row["on_minute"], row["off_minute"]
        if on is None or off is None:
            continue
        length = lengths.get(game, 90)
        on, off = max(0, on), min(length, off)
        if off <= on:
            continue  # a change recorded past full time buys nobody any minutes
        spells[game][sides[game][row["side"]]].append((row["player"], on, off))

    goals = collections.defaultdict(lambda: ([], []))
    for row in conn.execute(GOAL_MINUTES):
        game = row["game_id"]
        if game in wanted and row["minute"] is not None:
            goals[game][sides[game][row["side"]]].append(row["minute"])

    rows = []
    for game, match in wanted.items():
        first, second = spells.get(game, ([], []))
        if not first or not second:
            continue
        if sum(1 for _, on, _ in first if on == 0) != 11:
            continue
        if sum(1 for _, on, _ in second if on == 0) != 11:
            continue

        length = lengths.get(game, 90)
        cuts = {0, length}
        for side in (first, second):
            for _, on, off in side:
                if 0 < on < length:
                    cuts.add(on)
                if 0 < off < length:
                    cuts.add(off)
        cuts = sorted(cuts)

        scored = goals.get(game, ([], []))
        home = 1 if match["home"] == 0 else (-1 if match["home"] == 1 else 0)
        made = []
        for start, end in zip(cuts, cuts[1:]):
            on_first = [p for p, on, off in first if on <= start < off]
            on_second = [p for p, on, off in second if on <= start < off]
            if not on_first or not on_second:
                continue
            # A goal on a boundary minute belongs to the segment ending there:
            # the change is recorded at the minute it took effect.
            difference = (sum(1 for m in scored[0] if start < m <= end) -
                          sum(1 for m in scored[1] if start < m <= end))
            made.append(Segment(game, match["year"], match["series_id"],
                                match["clubs"], home, end - start, difference,
                                tuple(on_first), tuple(on_second)))
        if reconcile:
            recorded = match["goals"][0] - match["goals"][1]
            if sum(part.difference for part in made) != recorded:
                continue
        rows.extend(made)
    return rows


def minutes(rows):
    """``{player: minutes}`` over the given segments."""
    played = collections.Counter()
    for row in rows:
        for player in row.first:
            played[player] += row.minutes
        for player in row.second:
            played[player] += row.minutes
    return played


class Design:
    """Sparse design for a set of segments, plus the response vector.

    Column order is players, then home, then clubs. Home is left unpenalised;
    it is one column estimated from thousands of segments and needs no help.
    """

    def __init__(self, rows, players, clubs=None):
        self.players = players
        self.clubs = clubs or {}
        self.home_column = len(players)
        self.club_base = self.home_column + 1
        self.columns = self.club_base + len(self.clubs)
        self.rows = []
        self.y = []
        for row in rows:
            share = row.minutes / FULL_MATCH
            entries = []
            for player in row.first:
                column = players.get(player)
                if column is not None:
                    entries.append((column, share))
            for player in row.second:
                column = players.get(player)
                if column is not None:
                    entries.append((column, -share))
            if row.home:
                entries.append((self.home_column, share * row.home))
            if self.clubs:
                for club, sign in zip(row.clubs, (1, -1)):
                    column = self.clubs.get(club)
                    if column is not None:
                        entries.append((self.club_base + column, share * sign))
            self.rows.append(entries)
            self.y.append(float(row.difference))

    def penalties(self, player_penalty=PLAYER_PENALTY, club_penalty=CLUB_PENALTY):
        values = [player_penalty] * self.columns
        values[self.home_column] = 0.0
        for index in range(self.club_base, self.columns):
            values[index] = club_penalty
        return values

    def normal_rhs(self):
        """``X' y``."""
        rhs = [0.0] * self.columns
        for entries, target in zip(self.rows, self.y):
            if target:
                for column, value in entries:
                    rhs[column] += value * target
        return rhs

    def multiply(self, vector, penalties):
        """``(X'X + diag(penalties)) v`` without ever forming ``X'X``."""
        out = [penalty * component
               for penalty, component in zip(penalties, vector)]
        for entries in self.rows:
            total = 0.0
            for column, value in entries:
                total += value * vector[column]
            if total:
                for column, value in entries:
                    out[column] += value * total
        return out

    def predict(self, coefficients):
        return [sum(value * coefficients[column] for column, value in entries)
                for entries in self.rows]


def solve(design, penalties, tolerance=1e-10, iterations=1000):
    """Conjugate gradient on the ridge normal equations."""
    rhs = design.normal_rhs()
    coefficients = [0.0] * design.columns
    residual = list(rhs)
    direction = list(residual)
    squared = sum(value * value for value in residual)
    initial = squared
    if initial == 0.0:
        return coefficients
    for _ in range(iterations):
        product = design.multiply(direction, penalties)
        denominator = sum(a * b for a, b in zip(direction, product))
        if denominator <= 0.0:
            break
        step = squared / denominator
        for index in range(design.columns):
            coefficients[index] += step * direction[index]
            residual[index] -= step * product[index]
        updated = sum(value * value for value in residual)
        if updated <= tolerance * initial:
            break
        ratio = updated / squared
        for index in range(design.columns):
            direction[index] = residual[index] + ratio * direction[index]
        squared = updated
    return coefficients


def fit(rows, min_minutes=MIN_MINUTES, with_clubs=True,
        player_penalty=PLAYER_PENALTY, club_penalty=CLUB_PENALTY):
    """Fit ratings over ``rows``.

    Returns ``(ratings, home, design, coefficients)`` where ``ratings`` maps a
    player to their goals-per-90 effect on their side's goal difference.
    """
    played = minutes(rows)
    players = {player: index for index, player in
               enumerate(sorted(p for p in played if played[p] >= min_minutes))}
    clubs = None
    if with_clubs:
        clubs = {club: index for index, club in
                 enumerate(sorted({club for row in rows for club in row.clubs}))}
    design = Design(rows, players, clubs)
    coefficients = solve(design, design.penalties(player_penalty, club_penalty))
    ratings = {player: coefficients[column] for player, column in players.items()}
    return ratings, coefficients[design.home_column], design, coefficients


def by_match(rows, predictions):
    """Sum segment values up to whole matches: ``{game: (actual, predicted)}``."""
    totals = collections.OrderedDict()
    for row, predicted in zip(rows, predictions):
        actual, running = totals.get(row.game, (0.0, 0.0))
        totals[row.game] = (actual + row.difference, running + predicted)
    return totals


def _mean_square(totals):
    return sum((actual - predicted) ** 2 for actual, predicted in totals.values()) / len(totals)


def folds(rows, count=5, seed=20260901):
    """Grouped folds: every segment of a match lands in the same fold."""
    games = sorted({row.game for row in rows})
    random.Random(seed).shuffle(games)
    assigned = {game: index % count for index, game in enumerate(games)}
    return [([row for row in rows if assigned[row.game] != fold],
             [row for row in rows if assigned[row.game] == fold])
            for fold in range(count)]


def validate(rows, count=5, min_minutes=MIN_MINUTES,
             player_penalty=PLAYER_PENALTY, club_penalty=CLUB_PENALTY):
    """Grouped cross-validation, reported as match goal-difference error.

    Returns ``{model: mean squared error}`` for the zero model, clubs alone,
    players alone and both. Aggregate figures only, so this is the part that can
    be published.
    """
    baseline = _mean_square(by_match(rows, [0.0] * len(rows)))
    scores = {"zero": baseline}
    for name, use_players, use_clubs in (("clubs", False, True),
                                         ("players", True, False),
                                         ("clubs+players", True, True)):
        total, matches = 0.0, 0
        for train, test in folds(rows, count):
            played = minutes(train)
            players = ({player: index for index, player in
                        enumerate(sorted(p for p in played if played[p] >= min_minutes))}
                       if use_players else {})
            clubs = ({club: index for index, club in
                      enumerate(sorted({club for row in train for club in row.clubs}))}
                     if use_clubs else None)
            design = Design(train, players, clubs)
            coefficients = solve(design, design.penalties(player_penalty, club_penalty))
            held = Design(test, players, clubs)
            totals = by_match(test, held.predict(coefficients))
            total += sum((actual - predicted) ** 2 for actual, predicted in totals.values())
            matches += len(totals)
        scores[name] = total / matches
    return scores
