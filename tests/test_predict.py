"""Forecasting: home inference, model fitting, and the walk-forward harness.

Invented clubs, invented fixtures, no network.
"""

import datetime
import math
import unittest

from togakuren import db, predict


def match(first, second, goals=None, day=1, month=4, year="2099", venue=None,
          played=True, kind="league", game_id=None):
    return {
        "game_id": game_id or f"{first}-{second}-{month}-{day}",
        "date": datetime.date(int(year), month, day),
        "clubs": (first, second),
        "names": (first.title(), second.title()),
        "goals": goals if goals is not None else (0, 0),
        "home": None,
        "played": played,
        "year": year,
        "type": kind,
        "division": "1部",
        "series_id": f"series-{year}",
        "series_name": "1部リーグ",
    }


def season(strong, weak, rounds=8, year="2099", month=4):
    """A one-sided series: ``strong`` wins every fixture 3-0."""
    out = []
    for index in range(rounds):
        out.append(match(strong, weak, (3, 0), day=1 + index, month=month, year=year,
                         game_id=f"{year}-{month}-{index}a"))
        out.append(match(weak, strong, (0, 3), day=1 + index, month=month, year=year,
                         game_id=f"{year}-{month}-{index}b"))
    return out


class VenueOwnership(unittest.TestCase):
    def _fixtures(self, rows):
        return [[{"venue": venue, "club": home}, {"venue": venue, "club": away}]
                for venue, home, away in rows]

    def test_a_repeatedly_used_ground_is_assigned_to_its_club(self):
        owners = predict.venue_owners(self._fixtures([
            ("Alpha Ground", "alpha", "beta"),
            ("Alpha Ground", "alpha", "gamma"),
            ("Alpha Ground", "alpha", "delta"),
        ]))
        self.assertEqual(owners, {"Alpha Ground": "alpha"})

    def test_a_shared_ground_belongs_to_nobody(self):
        owners = predict.venue_owners(self._fixtures([
            ("City Stadium", "alpha", "beta"),
            ("City Stadium", "gamma", "delta"),
            ("City Stadium", "epsilon", "zeta"),
        ]))
        self.assertEqual(owners, {})

    def test_one_visit_is_not_enough_to_claim_a_ground(self):
        owners = predict.venue_owners(self._fixtures([("Alpha Ground", "alpha", "beta")]))
        self.assertEqual(owners, {})


class Loading(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.conn.execute(
            "INSERT INTO series (id, year, name, short_name, type, division)"
            " VALUES ('s1', '2099', 'Example', '1部リーグ', 'league', '1部')"
        )
        for pk, club in (("t-a", "100"), ("t-b", "200")):
            self.conn.execute(
                "INSERT INTO teams (id, series_id, team_id, name, short_name)"
                " VALUES (?, 's1', ?, ?, ?)", (pk, club, pk, pk)
            )
        for index in range(4):
            self.conn.execute(
                "INSERT INTO games (id, series_id, section, kickoff, venue, game_over, length)"
                " VALUES (?, 's1', '1', ?, 'Alpha Ground', 1, 90)",
                (f"g{index}", f"2099-04-0{index + 1} 13:00:00"),
            )
            self.conn.execute(
                "INSERT INTO game_teams (id, game_id, series_id, team_pk, score)"
                " VALUES (?, ?, 's1', 't-a', 2)", (f"g{index}-a", f"g{index}")
            )
            self.conn.execute(
                "INSERT INTO game_teams (id, game_id, series_id, team_pk, score)"
                " VALUES (?, ?, 's1', 't-b', 1)", (f"g{index}-b", f"g{index}")
            )
        self.conn.execute(
            "INSERT INTO games (id, series_id, section, kickoff, venue, game_over, length)"
            " VALUES ('g9', 's1', '9', '2099-05-01 13:00:00', 'Alpha Ground', 0, 90)"
        )
        self.conn.execute(
            "INSERT INTO game_teams (id, game_id, series_id, team_pk) VALUES ('g9-a', 'g9', 's1', 't-b')"
        )
        self.conn.execute(
            "INSERT INTO game_teams (id, game_id, series_id, team_pk) VALUES ('g9-b', 'g9', 's1', 't-a')"
        )
        self.conn.commit()

    def test_the_club_that_owns_the_ground_is_marked_at_home(self):
        played = [m for m in predict.load(self.conn) if m["played"]]
        self.assertEqual({m["home"] for m in played}, {0})

    def test_home_follows_the_club_not_the_listing_order(self):
        upcoming = predict.upcoming(predict.load(self.conn))
        self.assertEqual(upcoming[0]["clubs"], ("200", "100"))
        self.assertEqual(upcoming[0]["home"], 1)

    def test_fixtures_without_a_result_are_kept_for_forecasting(self):
        matches = predict.load(self.conn)
        self.assertEqual(len(matches), 5)
        self.assertEqual([m["goals"] for m in matches if not m["played"]], [(None, None)])

    def test_a_fixture_still_holding_its_provisional_date_is_not_in_the_past(self):
        matches = predict.load(self.conn)
        cutoff = predict.as_of(matches)
        self.assertEqual(cutoff, datetime.date(2099, 4, 5))
        stale = dict(matches[0], played=False)
        self.assertTrue(predict.undated(stale, cutoff))


class Scoring(unittest.TestCase):
    def test_a_certain_and_correct_forecast_scores_zero(self):
        self.assertAlmostEqual(predict.log_loss([[1.0, 0.0, 0.0]], [0]), 0.0)
        self.assertAlmostEqual(predict.brier([[1.0, 0.0, 0.0]], [0]), 0.0)

    def test_knowing_nothing_costs_the_log_of_three(self):
        third = [1 / 3, 1 / 3, 1 / 3]
        self.assertAlmostEqual(predict.log_loss([third] * 3, [0, 1, 2]), math.log(3))

    def test_a_certain_and_wrong_forecast_is_penalised_but_finite(self):
        self.assertGreater(predict.log_loss([[1.0, 0.0, 0.0]], [2]), 30)

    def test_calibration_bands_report_predicted_against_observed(self):
        rows = predict.calibration([[0.9, 0.05, 0.05]] * 10, [0] * 10)
        top = [row for row in rows if row[0] >= 0.9][0]
        self.assertEqual(top[2], 10)
        self.assertAlmostEqual(top[3], 0.9)
        self.assertAlmostEqual(top[4], 1.0)


class Models(unittest.TestCase):
    def test_the_prior_converges_on_the_frequencies_it_is_shown(self):
        model = predict.Prior()
        for _ in range(300):
            model.observe(match("a", "b", (1, 0)))
        self.assertGreater(model.predict(match("a", "b"))[predict.FIRST_WIN], 0.9)

    def test_elo_moves_the_winner_up_and_the_loser_down(self):
        model = predict.Elo()
        model.observe(match("a", "b", (2, 0)))
        self.assertGreater(model.ratings["a"], 1500.0)
        self.assertAlmostEqual(model.ratings["a"] - 1500.0, 1500.0 - model.ratings["b"])

    def test_elo_full_regression_forgets_the_previous_season(self):
        model = predict.Elo(regress=1.0)
        model.observe(match("a", "b", (5, 0), year="2098"))
        self.assertGreater(model.ratings["a"], 1500.0)
        model.observe(match("a", "b", (0, 0), year="2099"))
        self.assertAlmostEqual(model.ratings["a"], 1500.0, places=0)

    def test_poisson_separates_a_dominant_club_from_its_opponents(self):
        model = predict.Poisson(home=False)
        for fixture in (season("alpha", "beta", rounds=10) + season("alpha", "gamma", rounds=10)
                        + season("beta", "gamma", rounds=10)):
            model.observe(fixture)
        model.fit(datetime.date(2099, 4, 20))
        self.assertGreater(model.attack["alpha"], model.attack["beta"])
        self.assertGreater(model.defence["alpha"], model.defence["gamma"])
        chances = model.predict(match("alpha", "gamma"))
        self.assertGreater(chances[predict.FIRST_WIN], 0.8)

    def test_poisson_probabilities_are_a_distribution(self):
        model = predict.Poisson(rho=0.25)
        for fixture in season("alpha", "beta", rounds=30):
            model.observe(fixture)
        model.fit(datetime.date(2099, 5, 1))
        chances = model.predict(match("alpha", "beta"))
        self.assertAlmostEqual(sum(chances), 1.0, places=9)
        self.assertTrue(all(value >= 0 for value in chances))

    def test_the_dixon_coles_term_never_turns_a_scoreline_negative(self):
        # A high-scoring fixture drives the raw 0-0 multiplier below zero.
        self.assertGreater(predict._tau(0, 0, 6.0, 6.0, 0.25), 0)

    def test_an_unfitted_club_still_gets_a_usable_forecast(self):
        model = predict.Poisson()
        chances = model.predict(match("never", "seen"))
        self.assertAlmostEqual(sum(chances), 1.0, places=9)

    def test_recent_form_outweighs_an_old_reputation(self):
        recent, stale = predict.Poisson(half_life=30, home=False), predict.Poisson(half_life=3650, home=False)
        history = season("alpha", "beta", rounds=15, month=1) + season("beta", "alpha", rounds=15, month=6)
        for model in (recent, stale):
            for fixture in history:
                model.observe(fixture)
            model.fit(datetime.date(2099, 7, 1))
        self.assertGreater(recent.attack["beta"], stale.attack["beta"])


class WalkForward(unittest.TestCase):
    def test_a_fixture_is_never_predicted_by_a_model_that_has_seen_it(self):
        seen = []

        class Spy:
            name = "spy"
            def predict(self, fixture):
                assert fixture["game_id"] not in seen, "the model was shown the answer first"
                return [1 / 3, 1 / 3, 1 / 3]
            def observe(self, fixture):
                seen.append(fixture["game_id"])

        matches = season("alpha", "beta", rounds=5)
        predictions, actuals, scored = predict.walk_forward([Spy()], matches, start="2099")
        self.assertEqual(len(actuals), len(matches))
        self.assertEqual(len(seen), len(matches))

    def test_only_the_requested_seasons_are_scored(self):
        matches = season("alpha", "beta", rounds=3, year="2098") + season("alpha", "beta", rounds=3)
        _, actuals, scored = predict.walk_forward([predict.Prior()], matches, start="2099")
        self.assertEqual(len(actuals), 6)
        self.assertTrue(all(fixture["year"] == "2099" for fixture in scored))

    def test_cup_ties_can_be_left_out_of_the_scoring(self):
        matches = season("alpha", "beta", rounds=2)
        matches.append(match("alpha", "gamma", (1, 0), day=20, kind="tournament"))
        _, actuals, _ = predict.walk_forward(
            [predict.Prior()], matches, start="2099", keep=lambda m: m["type"] == "league"
        )
        self.assertEqual(len(actuals), 4)


class Projection(unittest.TestCase):
    def test_the_table_counts_points_and_goal_difference(self):
        rows = predict.table([match("alpha", "beta", (3, 0)), match("beta", "alpha", (1, 1), day=2)])
        self.assertEqual(rows["alpha"], [2, 4, 3, 4])
        self.assertEqual(rows["beta"], [2, 1, -3, 1])

    def test_simulating_a_finished_season_leaves_the_table_alone(self):
        played = [match("alpha", "beta", (3, 0))]
        points, positions = predict.simulate(predict.Prior(), played, [], runs=50)
        self.assertEqual(points["alpha"], 3.0)
        self.assertEqual(positions["alpha"][1], 50)

    def test_a_dominant_club_usually_finishes_top(self):
        played = season("alpha", "beta", rounds=30)
        model = predict.Poisson(home=False)
        for fixture in played:
            model.observe(fixture)
        model.fit(datetime.date(2099, 5, 10))
        remaining = [match("alpha", "beta", played=False, day=20, game_id="last")]
        _, positions = predict.simulate(model, played, remaining, runs=200)
        self.assertEqual(sum(positions["alpha"].values()), 200)
        self.assertGreater(positions["alpha"][1] / 200, 0.9)


if __name__ == "__main__":
    unittest.main()
