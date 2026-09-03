"""Forecasting match outcomes from the fixtures already loaded.

Everything the federation publishes is a record of what happened. This module is
the one part of the tool that makes a claim about what has not happened yet, so it
is built to be checked: every model is scored against the class prior by
walk-forward validation, and the CLI reports both.

Three models, each of which has to beat the one before it to be worth keeping:

* :class:`Prior` — the running frequency of home win / draw / away win. The
  number every other model must beat.
* :class:`Elo` — one rating per club, updated by result and margin.
* :class:`Poisson` — attack and defence strengths per club fitted by maximum
  likelihood with exponential time decay, then a scoreline distribution. Fitting
  is coordinate ascent with a closed form for every parameter, so this needs no
  optimiser and no dependency.

Home advantage is a special case here. The API records a venue but never a host,
so which side is at home is inferred from the venue (see :func:`venue_owners`)
and is unknown for rather more than half the fixtures.
"""

import collections
import datetime
import math
import random

FIRST_WIN, DRAW, SECOND_WIN = 0, 1, 2

#: Highest expected-goals rate a fitted model is allowed to claim for one side.
RATE_CAP = 8.0

#: Smallest value the Dixon-Coles multiplier may take, so no scoreline is ever
#: assigned a negative probability.
TAU_FLOOR = 0.01

MATCHES = """
SELECT g.id           AS game_id,
       g.venue        AS venue,
       g.kickoff      AS kickoff,
       g.game_over    AS played,
       s.year         AS year,
       s.type         AS type,
       s.division     AS division,
       s.short_name   AS series_name,
       s.id           AS series_id,
       gt.rowid       AS side,
       gt.score       AS score,
       t.team_id      AS club,
       t.short_name   AS club_name
FROM games g
JOIN series s       ON s.id = g.series_id
JOIN game_teams gt  ON gt.game_id = g.id
LEFT JOIN teams t   ON t.id = gt.team_pk
ORDER BY g.id, gt.rowid
"""

#: A venue counts as a club's ground once it has hosted this many fixtures and
#: that club was involved in this share of them.
VENUE_MIN_FIXTURES = 3
VENUE_MIN_SHARE = 0.75


def venue_owners(fixtures):
    """Work out which club, if any, each venue belongs to.

    The federation records a venue string and no host. Most grounds are named
    after the university that owns them, but not all — ``NICHIBUN SAKURA FIELD``
    is one club's home ground and contains no part of its name — so ownership is
    inferred from use instead of from the string: a venue that has hosted several
    fixtures, nearly all of them involving the same club, is that club's ground.

    Returns a ``{venue: club_id}`` mapping.
    """
    used = collections.Counter()
    seen = collections.defaultdict(collections.Counter)
    for sides in fixtures:
        venue = (sides[0]["venue"] or "").strip()
        if not venue or len(sides) != 2:
            continue
        used[venue] += 1
        for side in sides:
            if side["club"]:
                seen[venue][side["club"]] += 1
    owners = {}
    for venue, total in used.items():
        if total < VENUE_MIN_FIXTURES:
            continue
        club, hosted = seen[venue].most_common(1)[0]
        if hosted / total >= VENUE_MIN_SHARE:
            owners[venue] = club
    return owners


def load(conn):
    """Every fixture as one row, oldest first.

    Each row is a dict with ``clubs`` and ``goals`` as two-tuples in the order the
    federation stores them, ``home`` as the index of the home side or ``None``
    when the venue does not identify one, and ``played`` for whether the result is
    in. Unplayed fixtures are included — they are what there is to forecast.
    """
    grouped = collections.OrderedDict()
    for row in conn.execute(MATCHES):
        grouped.setdefault(row["game_id"], []).append(row)

    fixtures = [sides for sides in grouped.values() if len(sides) == 2]
    owners = venue_owners(fixtures)

    matches = []
    for sides in fixtures:
        first, second = sides
        if not (first["club"] and second["club"]):
            continue
        try:
            date = datetime.date.fromisoformat((first["kickoff"] or "")[:10])
        except ValueError:
            continue
        played = bool(first["played"])
        try:
            goals = (int(first["score"]), int(second["score"]))
        except (TypeError, ValueError):
            if played:
                continue  # finished but unscored: nothing to learn from
            goals = (None, None)
        owner = owners.get((first["venue"] or "").strip())
        home = 0 if owner == first["club"] else (1 if owner == second["club"] else None)
        matches.append(
            {
                "game_id": first["game_id"],
                "date": date,
                "clubs": (first["club"], second["club"]),
                "names": (first["club_name"], second["club_name"]),
                "goals": goals,
                "home": home,
                "played": played,
                "year": first["year"],
                "type": first["type"],
                "division": first["division"],
                "series_id": first["series_id"],
                "series_name": first["series_name"],
            }
        )
    matches.sort(key=lambda match: (match["date"], match["game_id"]))
    return matches


def outcome(match):
    """Which of the three outcomes happened, from the first-listed side's view."""
    first, second = match["goals"]
    return FIRST_WIN if first > second else (DRAW if first == second else SECOND_WIN)


# -- scoring ---------------------------------------------------------------

_FLOOR = 1e-15


def log_loss(predictions, actuals):
    """Mean negative log probability of what actually happened."""
    return -sum(
        math.log(max(p[y], _FLOOR)) for p, y in zip(predictions, actuals)
    ) / len(actuals)


def brier(predictions, actuals):
    total = 0.0
    for p, y in zip(predictions, actuals):
        total += sum((p[k] - (1.0 if k == y else 0.0)) ** 2 for k in range(3))
    return total / len(actuals)


def accuracy(predictions, actuals):
    return sum(
        1 for p, y in zip(predictions, actuals)
        if max(range(3), key=lambda k: p[k]) == y
    ) / len(actuals)


def calibration(predictions, actuals, bins=10):
    """Predicted probability against observed frequency, in ``bins`` bands.

    Every outcome of every fixture contributes one point, so a model that is
    confident and right and one that is confident and wrong separate here even
    when their log loss is similar.
    """
    buckets = collections.defaultdict(lambda: [0, 0.0, 0])
    for p, y in zip(predictions, actuals):
        for k in range(3):
            index = min(bins - 1, int(p[k] * bins))
            buckets[index][0] += 1
            buckets[index][1] += p[k]
            buckets[index][2] += 1 if k == y else 0
    return [
        (index / bins, (index + 1) / bins, count, predicted / count, hits / count)
        for index, (count, predicted, hits) in sorted(buckets.items())
    ]


# -- models ----------------------------------------------------------------

class Prior:
    """Running frequency of the three outcomes. The baseline to beat."""

    def __init__(self, name="prior"):
        self.name = name
        self._counts = [1.0, 1.0, 1.0]   # start uniform rather than undefined

    def predict(self, match):
        total = sum(self._counts)
        return [count / total for count in self._counts]

    def observe(self, match):
        self._counts[outcome(match)] += 1


class Elo:
    """One rating per club, updated by result and margin of victory.

    Args:
        k: update size.
        home: rating points added to a known home side.
        draw: half-width of the draw band in the ordered logistic, in logits.
        regress: fraction of a club's rating pulled back to the mean between
            seasons. University squads turn over every year, so how much of last
            season should carry over is a real question rather than a detail;
            it is left as a parameter so the answer can be measured.
    """

    SCALE = 400.0

    def __init__(self, k=40.0, home=40.0, draw=0.35, regress=0.0, margin=True, name=None):
        self.k, self.home, self.draw, self.regress, self.margin = k, home, draw, regress, margin
        self.name = name or f"elo-k{k:g}"
        self.ratings = collections.defaultdict(lambda: 1500.0)
        self._season = None

    def edge(self, match):
        first, second = match["clubs"]
        edge = self.ratings[first] - self.ratings[second]
        if match["home"] == 0:
            edge += self.home
        elif match["home"] == 1:
            edge -= self.home
        return edge

    def predict(self, match):
        logit = self.edge(match) / self.SCALE * math.log(10)
        first = 1.0 / (1.0 + math.exp(-(logit - self.draw)))
        second = 1.0 / (1.0 + math.exp(-(-logit - self.draw)))
        drawn = max(_FLOOR, 1.0 - first - second)
        total = first + drawn + second
        return [first / total, drawn / total, second / total]

    def observe(self, match):
        if self.regress and match["year"] != self._season:
            if self._season is not None:
                for club in list(self.ratings):
                    self.ratings[club] = 1500.0 + (self.ratings[club] - 1500.0) * (1 - self.regress)
            self._season = match["year"]
        first, second = match["clubs"]
        for_, against = match["goals"]
        expected = 1.0 / (1.0 + 10 ** (-self.edge(match) / self.SCALE))
        actual = 1.0 if for_ > against else (0.5 if for_ == against else 0.0)
        weight = math.log(abs(for_ - against) + 1) if self.margin else 1.0
        change = self.k * weight * (actual - expected)
        self.ratings[first] += change
        self.ratings[second] -= change


class Poisson:
    """Attack and defence strengths per club, fitted by weighted maximum likelihood.

    Goals scored by club *i* against club *j* are modelled as Poisson with rate
    ``exp(mu + attack_i - defence_j + home)``. Every parameter has a closed-form
    update given the others, so the fit is coordinate ascent and needs nothing
    beyond the standard library.

    Args:
        half_life: days after which a fixture carries half the weight. Squads turn
            over every year, so old matches describe a different team.
        home: include a home-advantage term. It applies only to the fixtures whose
            venue identifies a host.
        rho: Dixon-Coles correction for the dependence between low scores. Zero
            leaves the two sides independent.
        goal_cap: highest scoreline considered when the rates are turned into
            outcome probabilities.
    """

    #: Defaults chosen on 2022-2024 alone and then left alone, so the numbers
    #: reported for 2025-2026 in docs/PREDICTION.en.md are out of sample.
    def __init__(self, half_life=180.0, home=True, rho=0.2, goal_cap=15,
                 iterations=40, warm_iterations=20, name=None):
        self.half_life, self.use_home, self.rho = half_life, home, rho
        self.goal_cap, self.iterations, self.warm_iterations = goal_cap, iterations, warm_iterations
        self.name = name or f"poisson-{half_life:g}d"
        self.attack = collections.defaultdict(float)
        self.defence = collections.defaultdict(float)
        self.baseline = math.log(1.8)
        self.advantage = 0.0
        self._history = []
        self._fitted = False

    def observe(self, match):
        self._history.append(match)

    def fit(self, asof):
        """Refit on everything observed so far, weighted towards ``asof``."""
        if len(self._history) < 50:
            return
        decay = math.log(2) / self.half_life
        # One entry per team per fixture: who attacked, who defended, how many.
        sides = []
        for match in self._history:
            weight = math.exp(-decay * (asof - match["date"]).days)
            if weight < 1e-4:
                continue
            first, second = match["clubs"]
            for_, against = match["goals"]
            sign = 1 if match["home"] == 0 else (-1 if match["home"] == 1 else 0)
            sides.append((first, second, for_, sign, weight))
            sides.append((second, first, against, -sign, weight))
        if not sides:
            return

        clubs = {club for side in sides for club in side[:2]}
        attack = {club: self.attack.get(club, 0.0) for club in clubs}
        defence = {club: self.defence.get(club, 0.0) for club in clubs}
        baseline, advantage = self.baseline, self.advantage
        if not self.use_home:
            advantage = 0.0

        for _ in range(self.iterations if not self._fitted else self.warm_iterations):
            scored = sum(weight * goals for _, _, goals, _, weight in sides)
            expected = sum(
                weight * math.exp(attack[a] - defence[d] + advantage * sign)
                for a, d, _, sign, weight in sides
            )
            if expected > 0 and scored > 0:
                baseline = math.log(scored / expected)

            # Attack: the rate a club scores at, given everyone it has faced.
            scored_by = collections.defaultdict(float)
            expected_by = collections.defaultdict(float)
            for a, d, goals, sign, weight in sides:
                scored_by[a] += weight * goals
                expected_by[a] += weight * math.exp(baseline - defence[d] + advantage * sign)
            for club in clubs:
                if scored_by[club] > 0 and expected_by[club] > 0:
                    attack[club] = math.log(scored_by[club] / expected_by[club])

            # Defence: the same, from the conceding side.
            conceded_by = collections.defaultdict(float)
            expected_by = collections.defaultdict(float)
            for a, d, goals, sign, weight in sides:
                conceded_by[d] += weight * goals
                expected_by[d] += weight * math.exp(baseline + attack[a] + advantage * sign)
            for club in clubs:
                if conceded_by[club] > 0 and expected_by[club] > 0:
                    defence[club] = -math.log(conceded_by[club] / expected_by[club])

            # Attack and defence are only identified up to a shift; park it in mu.
            mean_attack = sum(attack.values()) / len(attack)
            mean_defence = sum(defence.values()) / len(defence)
            for club in clubs:
                attack[club] -= mean_attack
                defence[club] -= mean_defence
            baseline += mean_attack - mean_defence

            if self.use_home:
                gradient = curvature = 0.0
                for a, d, goals, sign, weight in sides:
                    if not sign:
                        continue
                    rate = math.exp(baseline + attack[a] - defence[d] + advantage * sign)
                    gradient += weight * sign * (goals - rate)
                    curvature += weight * rate
                if curvature > 0:
                    advantage += gradient / curvature

        self.attack, self.defence = attack, defence
        self.baseline, self.advantage = baseline, advantage
        self._fitted = True

    def rates(self, match):
        """Expected goals for each side, in the stored order.

        A club with two matches played can end up with an extreme strength, so
        the rate is capped. Nothing in this league has ever averaged eight goals
        a game; a fit that says so is describing a small sample, not a team.
        """
        first, second = match["clubs"]
        sign = 1 if match["home"] == 0 else (-1 if match["home"] == 1 else 0)
        advantage = self.advantage * sign if self.use_home else 0.0
        return (
            min(RATE_CAP, math.exp(self.baseline + self.attack.get(first, 0.0)
                                   - self.defence.get(second, 0.0) + advantage)),
            min(RATE_CAP, math.exp(self.baseline + self.attack.get(second, 0.0)
                                   - self.defence.get(first, 0.0) - advantage)),
        )

    def predict(self, match):
        first_rate, second_rate = self.rates(match)
        first = _poisson_pmf(first_rate, self.goal_cap)
        second = _poisson_pmf(second_rate, self.goal_cap)
        result = [0.0, 0.0, 0.0]
        for i, pi in enumerate(first):
            for j, pj in enumerate(second):
                joint = pi * pj
                if self.rho and i < 2 and j < 2:
                    joint *= _tau(i, j, first_rate, second_rate, self.rho)
                result[FIRST_WIN if i > j else (DRAW if i == j else SECOND_WIN)] += joint
        total = sum(result)
        return [value / total for value in result]


def _poisson_pmf(rate, cap):
    out = [math.exp(-rate)]
    for k in range(1, cap + 1):
        out.append(out[-1] * rate / k)
    return out


def _tau(i, j, first, second, rho):
    """Dixon-Coles adjustment to the four lowest scorelines.

    The correction is a multiplier, and for a high-scoring fixture the 0-0 term
    can go negative, which would hand back a negative probability. It is floored
    instead — the adjustment is meant for low-scoring games and simply has
    nothing to say about a fixture both sides are expected to score three in.
    """
    if i == 0 and j == 0:
        adjusted = 1 - first * second * rho
    elif i == 0 and j == 1:
        adjusted = 1 + first * rho
    elif i == 1 and j == 0:
        adjusted = 1 + second * rho
    else:
        adjusted = 1 - rho
    return max(TAU_FLOOR, adjusted)


# -- validation ------------------------------------------------------------

def walk_forward(models, matches, start=None, refit_days=7, keep=None):
    """Score models on fixtures they have not seen.

    Each fixture is predicted using only what happened before it, then handed to
    every model. There is no random split anywhere: team strength leaks the
    future, so a shuffled hold-out would flatter every model here.

    Args:
        models: objects with ``predict``/``observe`` (and optionally ``fit``).
        matches: output of :func:`load`, oldest first.
        start: season string; earlier fixtures train but are not scored.
        refit_days: how stale a fitted model may get before refitting.
        keep: predicate deciding which fixtures are scored.

    Returns ``(predictions_by_model, actuals, matches_scored)``.
    """
    predictions = {model.name: [] for model in models}
    actuals, scored = [], []
    for match in matches:
        if not match["played"]:
            continue
        # Refitting is on a calendar, not on which fixtures are being scored, so
        # narrowing the scored window cannot change the models' state.
        for model in models:
            fit = getattr(model, "fit", None)
            if fit is None:
                continue
            last = getattr(model, "_last_fit", None)
            if last is None or (match["date"] - last).days >= refit_days:
                fit(match["date"])
                model._last_fit = match["date"]
        if (start is None or match["year"] >= start) and (keep is None or keep(match)):
            for model in models:
                predictions[model.name].append(model.predict(match))
            actuals.append(outcome(match))
            scored.append(match)
        for model in models:
            model.observe(match)
    return predictions, actuals, scored


def fit_through(model, matches, asof):
    """Feed every fixture played before ``asof`` to ``model`` and fit it."""
    for match in matches:
        if match["played"] and match["date"] < asof:
            model.observe(match)
    fit = getattr(model, "fit", None)
    if fit is not None:
        fit(asof)
    return model


def as_of(matches):
    """The day after the last result, which is where a forecast starts from."""
    played = [match["date"] for match in matches if match["played"]]
    if not played:
        raise ValueError("no results loaded")
    return max(played) + datetime.timedelta(days=1)


def undated(match, cutoff):
    """Whether a fixture still to play has no real kickoff date.

    A fixture keeps the season's provisional date until the federation schedules
    it, so an unplayed fixture dated before the last result is not in the past —
    it is simply not scheduled yet, and 73 of the 128 outstanding fixtures were in
    that state in August 2026.
    """
    return match["date"] < cutoff


def upcoming(matches, series_id=None):
    """Fixtures with no result yet: scheduled ones first, then the unscheduled."""
    cutoff = as_of(matches)
    remaining = [
        match for match in matches
        if not match["played"] and (series_id is None or match["series_id"] == series_id)
    ]
    remaining.sort(key=lambda match: (undated(match, cutoff), match["date"], match["game_id"]))
    return remaining


# -- season projection -----------------------------------------------------

def table(matches):
    """League table computed from results: ``{club: [played, points, gd, gf]}``.

    Computed from the fixtures rather than read from ``standings`` so that a
    projection and the results it is built on can never disagree. On the 2026
    first division this reproduces the federation's own table exactly.
    """
    rows = collections.defaultdict(lambda: [0, 0, 0, 0])
    for match in matches:
        if not match["played"]:
            continue
        first, second = match["clubs"]
        for_, against = match["goals"]
        for club, scored, conceded in ((first, for_, against), (second, against, for_)):
            row = rows[club]
            row[0] += 1
            row[1] += 3 if scored > conceded else (1 if scored == conceded else 0)
            row[2] += scored - conceded
            row[3] += scored
    return rows


def simulate(model, played, remaining, runs=10000, seed=0):
    """Play the rest of a season ``runs`` times and count where each club lands.

    Each remaining fixture is drawn from the model's own outcome probabilities.
    Only the outcome is drawn, not the scoreline, so clubs level on points are
    separated by the goal difference they have already — good enough to rank a
    table, and not good enough to quote a goal difference from.

    Returns ``(expected_points, positions)`` where ``positions[club][place]`` is
    how often that club finished in that place, ``place`` counting from 1.
    """
    rng = random.Random(seed)
    start = table(played)
    clubs = sorted(set(start) | {club for match in remaining for club in match["clubs"]})
    odds = [(match["clubs"], model.predict(match)) for match in remaining]

    total_points = collections.Counter()
    positions = {club: collections.Counter() for club in clubs}
    for _ in range(runs):
        points = {club: start[club][1] for club in clubs}
        for (first, second), probabilities in odds:
            roll = rng.random()
            if roll < probabilities[FIRST_WIN]:
                points[first] += 3
            elif roll < probabilities[FIRST_WIN] + probabilities[DRAW]:
                points[first] += 1
                points[second] += 1
            else:
                points[second] += 3
        order = sorted(clubs, key=lambda club: (-points[club], -start[club][2]))
        for place, club in enumerate(order, start=1):
            positions[club][place] += 1
        total_points.update(points)
    return ({club: total_points[club] / runs for club in clubs}, positions)
