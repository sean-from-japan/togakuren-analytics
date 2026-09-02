"""The cross-league measurements, on leagues invented for the purpose.

Nothing here touches the network or a real league. Each test builds a season
whose answer is known by construction — every club identical, or one club made
better by a set amount — so the measurements can be checked against something
other than themselves.
"""
import datetime
import itertools
import math
import random
import unittest

from togakuren import compare


def season(year, clubs, rng, strength=None, division="1", rounds=2):
    """A round robin, once or twice round. ``strength`` biases scoring rate."""
    strength = strength or {}
    matches = []
    day = datetime.date(int(year), 3, 1)
    pairs = list(itertools.permutations(clubs, 2)) if rounds == 2 else \
        list(itertools.combinations(clubs, 2))
    for index, (home, away) in enumerate(pairs):
        day = day + datetime.timedelta(days=3)
        home_goals = rng.poisson_like(1.3 + strength.get(home, 0.0))
        away_goals = rng.poisson_like(1.1 + strength.get(away, 0.0))
        matches.append({
            "game_id": f"{year}-{division}-{index}",
            "date": day,
            "clubs": (home, away),
            "names": (home, away),
            "goals": (home_goals, away_goals),
            "home": 0,
            "played": True,
            "year": str(year),
            "type": "league",
            "division": division,
        })
    return matches


class Rng:
    """Deterministic Poisson counts, by inverting the CDF."""

    def __init__(self, seed):
        self.random = random.Random(seed)

    def poisson_like(self, rate):
        rate = max(rate, 0.05)
        target = self.random.random()
        term = cumulative = math.exp(-rate)
        count = 0
        while target > cumulative and count < 20:
            count += 1
            term *= rate / count
            cumulative += term
        return count


def league(years, clubs, seed, strength=None, division="1", rounds=2):
    rng = Rng(seed)
    return [match for year in years
            for match in season(year, clubs, rng, strength, division, rounds)]


CLUBS = [f"club-{index}" for index in range(10)]
YEARS = [2091, 2092, 2093, 2094, 2095]


class Balance(unittest.TestCase):
    def test_clubs_of_equal_strength_leave_almost_no_talent_spread(self):
        rows = league(YEARS, CLUBS, seed=1)
        found = compare.balance(rows)
        self.assertLess(found["talent_spread"], 0.06)
        self.assertLess(found["noll_scully"], 1.5)

    def test_one_strong_club_shows_up_as_spread(self):
        even = compare.balance(league(YEARS, CLUBS, seed=1))
        uneven = compare.balance(
            league(YEARS, CLUBS, seed=1, strength={"club-0": 1.6, "club-1": 1.2}))
        self.assertGreater(uneven["talent_spread"], even["talent_spread"])

    def test_a_short_season_is_not_made_to_look_balanced_by_being_short(self):
        """This is the whole reason the correction exists.

        The same clubs, the same strengths, played once round instead of twice.
        Noll-Scully moves a long way because its denominator grew; the corrected
        spread, which is a statement about the clubs, should barely move.
        """
        strength = {"club-0": 1.4, "club-1": 0.9, "club-9": -0.5}
        long_found = compare.balance(
            league(YEARS, CLUBS, seed=4, strength=strength, rounds=2), min_games=8)
        short_found = compare.balance(
            league(YEARS, CLUBS, seed=4, strength=strength, rounds=1), min_games=8)
        self.assertLess(short_found["fixtures_per_club"],
                        long_found["fixtures_per_club"])
        self.assertLess(
            abs(short_found["talent_spread"] - long_found["talent_spread"]),
            abs(short_found["noll_scully"] - long_found["noll_scully"]))

    def test_tiers_are_never_pooled_into_one_season(self):
        first = league(YEARS, CLUBS, seed=2, division="1")
        second = league(YEARS, [f"b{i}" for i in range(10)], seed=3, division="2")
        keys = compare.win_ratios(first + second)
        self.assertEqual(len(keys), 2 * len(YEARS))

    def test_a_season_too_small_to_measure_is_skipped(self):
        self.assertIsNone(compare.balance(league([2091], CLUBS[:3], seed=5)))


class Shape(unittest.TestCase):
    def test_draws_and_goals_are_counted_over_played_fixtures_only(self):
        rows = league([2091], CLUBS, seed=6)
        rows.append(dict(rows[0], game_id="unplayed", played=False,
                         goals=(None, None)))
        found = compare.shape(rows)
        self.assertEqual(found["fixtures"], len(rows) - 1)
        self.assertGreaterEqual(found["draw_rate"], 0.0)
        self.assertGreater(found["goals_per_fixture"], 0.0)


class Windows(unittest.TestCase):
    def test_the_first_season_trains_and_the_last_two_are_held_back(self):
        burn_in, tuning, test = compare.windows(league(YEARS, CLUBS, seed=7))
        self.assertEqual(burn_in, ["2091"])
        self.assertEqual(tuning, ["2092", "2093"])
        self.assertEqual(test, ["2094", "2095"])

    def test_too_few_seasons_is_refused(self):
        with self.assertRaises(ValueError):
            compare.windows(league([2091, 2092], CLUBS, seed=8))


class Profile(unittest.TestCase):
    def test_the_half_life_comes_from_the_tuning_seasons(self):
        rows = league(YEARS, CLUBS, seed=9, strength={"club-0": 1.5})
        found = compare.profile(rows, half_lives=(90, 365, 4000))
        self.assertIn(found["half_life"], (90, 365, 4000))
        self.assertEqual(found["test"], ["2094", "2095"])
        self.assertEqual(set(found["sweep"]), {"90", "365", "4000"})

    def test_a_league_with_a_dominant_club_is_predictable(self):
        """A model should beat the class prior when one club really is better."""
        rows = league(YEARS, CLUBS, seed=10,
                      strength={"club-0": 1.8, "club-1": 1.4, "club-9": -0.6})
        self.assertGreater(compare.profile(rows, half_lives=(365, 4000))["gain"], 0)

    def test_measure_returns_all_three_parts_of_a_row(self):
        rows = league(YEARS, CLUBS, seed=11)
        found = compare.measure(rows, half_lives=(365,))
        for key in ("gain", "talent_spread", "noll_scully", "draw_rate",
                    "goals_per_fixture", "half_life"):
            self.assertIn(key, found)


class Placement(unittest.TestCase):
    def rows(self):
        return [{"talent_spread": spread, "gain": -0.09 + 1.25 * spread + bump}
                for spread, bump in ((0.06, 0.002), (0.08, -0.003), (0.10, 0.001),
                                     (0.12, -0.002), (0.14, 0.003), (0.16, -0.001))]

    def test_the_line_recovers_the_slope_it_was_built_from(self):
        fitted = compare.line(self.rows())
        self.assertAlmostEqual(fitted["slope"], 1.25, places=1)
        self.assertLess(fitted["residual_sd"], 0.01)

    def test_a_league_on_the_line_has_a_small_residual(self):
        fitted = compare.line(self.rows())
        placed = compare.place({"talent_spread": 0.11,
                                "gain": -0.09 + 1.25 * 0.11}, fitted)
        self.assertLess(abs(placed["residual_sd"]), 2.0)
        self.assertTrue(placed["inside_reference_spread"])

    def test_a_league_above_the_line_is_reported_as_above_it(self):
        fitted = compare.line(self.rows())
        placed = compare.place({"talent_spread": 0.11,
                                "gain": -0.09 + 1.25 * 0.11 + 0.05}, fitted)
        self.assertGreater(placed["residual_sd"], 3.0)

    def test_a_spread_outside_the_reference_range_is_flagged(self):
        fitted = compare.line(self.rows())
        placed = compare.place({"talent_spread": 0.30, "gain": 0.3}, fitted)
        self.assertFalse(placed["inside_reference_spread"])

    def test_a_line_needs_more_than_two_points(self):
        with self.assertRaises(ValueError):
            compare.line(self.rows()[:2])


if __name__ == "__main__":
    unittest.main()
