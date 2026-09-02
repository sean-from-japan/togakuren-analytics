"""Placing a league among others by fitting the same model to all of them.

Applying a model to one league says nothing about the league. The same model
across many turns each one into a point on a map, and then a league has a
position rather than a set of numbers.

Two quantities do the work.

**Talent spread.** Noll and Scully's ratio divides the observed spread of win
ratios by the spread a league of identical clubs would show over a season of
that length. It is the standard measure and it is the wrong one here: a
university season is ten to twenty fixtures against thirty-four to forty-six, so
its larger denominator divides a genuinely wide spread back down to look
ordinary. Observed variance is talent plus the noise a season of that length
leaves behind, so subtracting the noise recovers what the clubs actually are:

    sd_talent = sqrt(sd_observed^2 - sd_ideal^2)

That decomposition is not new — it is Tango's and Mauboussin's, and James
Grayson and Martin Eastwood have both applied it to football. What is done here
is applying it, and the predictability measure below, to leagues that the
published comparisons leave out.

**Predictability.** How far a fitted model gets below the class prior, in nats,
on seasons whose half-life it was not chosen on. :mod:`togakuren.predict`
supplies the model; nothing about it is re-implemented here.

Everything in this module is league-level. No function takes or returns a
player.
"""
import collections
import math
import statistics

from . import predict

#: Half-lives searched on the tuning seasons, in days.
HALF_LIVES = (30, 45, 60, 90, 120, 180, 250, 365, 550, 800, 1200, 2000, 4000)

#: Seasons held back from the half-life search and scored afterwards.
TEST_SEASONS = 2

#: A season needs this many clubs, each with this many fixtures, to be measured.
MIN_CLUBS = 6
MIN_GAMES = 10


def win_ratios(matches):
    """``{(season, division): {club: [wins counting a draw a half, fixtures]}}``.

    Keyed by division as well as season on purpose. Pooling a pyramid's tiers
    into one season measures the gap between the tiers, not the balance inside
    any league.
    """
    tally = collections.defaultdict(
        lambda: collections.defaultdict(lambda: [0.0, 0]))
    for match in matches:
        if not match.get("played") or match["goals"][0] is None:
            continue
        first, second = match["clubs"]
        for_, against = match["goals"]
        result = 1.0 if for_ > against else (0.0 if for_ < against else 0.5)
        season = tally[(match["year"], match.get("division"))]
        season[first][0] += result
        season[first][1] += 1
        season[second][0] += 1.0 - result
        season[second][1] += 1
    return tally


def balance(matches, min_clubs=MIN_CLUBS, min_games=MIN_GAMES):
    """Noll-Scully and the noise-corrected talent spread, averaged over seasons.

    Returns ``None`` when no season is big enough to say anything.
    """
    seasons = []
    for clubs in win_ratios(matches).values():
        ratios = [won / games for won, games in clubs.values() if games >= min_games]
        played = [games for _, games in clubs.values() if games >= min_games]
        if len(ratios) < min_clubs:
            continue
        ideal = 0.5 / math.sqrt(statistics.mean(played))
        observed = statistics.pstdev(ratios)
        seasons.append((observed / ideal,
                        math.sqrt(max(observed ** 2 - ideal ** 2, 0.0)),
                        statistics.mean(played), len(ratios)))
    if not seasons:
        return None
    return {
        "noll_scully": statistics.mean(row[0] for row in seasons),
        "talent_spread": statistics.mean(row[1] for row in seasons),
        "fixtures_per_club": statistics.mean(row[2] for row in seasons),
        "clubs": statistics.mean(row[3] for row in seasons),
        "seasons": len(seasons),
    }


def shape(matches):
    """How often fixtures resolve, and how much is scored in them."""
    played = [m for m in matches if m.get("played") and m["goals"][0] is not None]
    if not played:
        return None
    drawn = sum(1 for m in played if m["goals"][0] == m["goals"][1])
    return {
        "draw_rate": drawn / len(played),
        "goals_per_fixture": sum(sum(m["goals"]) for m in played) / len(played),
        "fixtures": len(played),
    }


def windows(matches, test_seasons=TEST_SEASONS):
    """``(burn_in, tuning, test)`` season labels: hold back the last seasons.

    The first season only trains, because a model that has seen nothing is not
    being asked a fair question about the fixtures it opens on.
    """
    years = sorted({match["year"] for match in matches})
    if len(years) < test_seasons + 2:
        raise ValueError(f"need {test_seasons + 2} seasons, found {len(years)}")
    return years[:1], years[1:-test_seasons], years[-test_seasons:]


def _score(matches, half_life, tuning, test):
    """Log loss and accuracy per model over both windows, in one walk forward."""
    models = [predict.Prior(), predict.Elo(),
              predict.Poisson(half_life=half_life)]
    predictions, actuals, scored = predict.walk_forward(models, matches)
    out = {}
    for name, values in predictions.items():
        for label, seasons in (("tuning", set(tuning)), ("test", set(test))):
            picked = [(value, actual) for value, actual, match
                      in zip(values, actuals, scored) if match["year"] in seasons]
            if picked:
                out[(name, label)] = {
                    "log_loss": predict.log_loss([v for v, _ in picked],
                                                 [a for _, a in picked]),
                    "accuracy": predict.accuracy([v for v, _ in picked],
                                                 [a for _, a in picked]),
                    "fixtures": len(picked),
                }
    return out


def profile(matches, half_lives=HALF_LIVES, test_seasons=TEST_SEASONS):
    """Fit, choosing the half-life on the tuning seasons and scoring the rest.

    The returned ``gain`` is nats below the class prior on seasons the half-life
    was not chosen on, which is the number worth comparing across leagues.
    """
    burn_in, tuning, test = windows(matches, test_seasons)
    swept = {life: _score(matches, life, tuning, test) for life in half_lives}

    def tuned(life):
        return swept[life][(f"poisson-{life:g}d", "tuning")]["log_loss"]

    best = min(half_lives, key=tuned)
    chosen = swept[best]
    prior = chosen[("prior", "test")]
    poisson = chosen[(f"poisson-{best:g}d", "test")]
    longest = max(half_lives)
    return {
        "half_life": best,
        "burn_in": burn_in, "tuning": tuning, "test": test,
        "prior": prior["log_loss"],
        "elo": chosen[("elo-k40", "test")]["log_loss"],
        "poisson": poisson["log_loss"],
        "gain": prior["log_loss"] - poisson["log_loss"],
        "accuracy": poisson["accuracy"],
        "fixtures": prior["fixtures"],
        # The same model with its memory switched off, so the decay's worth is
        # readable rather than asserted.
        "without_decay": chosen and swept[longest][
            (f"poisson-{longest:g}d", "test")]["log_loss"],
        "sweep": {str(life): tuned(life) for life in half_lives},
    }


def measure(matches, **kwargs):
    """``profile`` plus ``balance`` plus ``shape`` for one league."""
    row = dict(profile(matches, **kwargs))
    row.update(balance(matches) or {})
    row.update(shape(matches) or {})
    return row


def line(rows):
    """Least squares of gain on talent spread, and the scatter about it.

    Fit this on the reference leagues alone. A league being placed must not help
    decide where the line goes.
    """
    points = [(row["talent_spread"], row["gain"]) for row in rows]
    if len(points) < 3:
        raise ValueError("need at least three leagues to fit a line")
    mean_x = statistics.mean(x for x, _ in points)
    mean_y = statistics.mean(y for _, y in points)
    sxx = sum((x - mean_x) ** 2 for x, _ in points)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / sxx
    intercept = mean_y - slope * mean_x
    residuals = [y - (intercept + slope * x) for x, y in points]
    return {
        "intercept": intercept,
        "slope": slope,
        "residual_sd": math.sqrt(sum(r * r for r in residuals) / (len(points) - 2)),
        "n": len(points),
        "spread": (min(x for x, _ in points), max(x for x, _ in points)),
    }


def place(row, fitted):
    """Where one league sits against a fitted reference line, in residual sd."""
    expected = fitted["intercept"] + fitted["slope"] * row["talent_spread"]
    low, high = fitted["spread"]
    return {
        "expected_gain": expected,
        "residual": row["gain"] - expected,
        "residual_sd": (row["gain"] - expected) / fitted["residual_sd"],
        "inside_reference_spread": low <= row["talent_spread"] <= high,
    }
