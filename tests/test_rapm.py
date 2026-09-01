"""Plus-minus ratings: segment extraction, the solver, and what it recovers.

Invented clubs, invented people, no network.
"""

import random
import unittest

from togakuren import db, rapm


class Builder:
    """A tiny in-memory database with one league and two clubs."""

    def __init__(self):
        self.conn = db.connect(":memory:")
        self.conn.execute(
            "INSERT INTO series (id, year, name, short_name, type, division)"
            " VALUES ('s1', '2099', 'Example', '1部リーグ', 'league', '1部')")
        for pk, club in (("t-a", "100"), ("t-b", "200")):
            self.conn.execute(
                "INSERT INTO teams (id, series_id, team_id, name, short_name)"
                " VALUES (?, 's1', ?, ?, ?)", (pk, club, pk, pk))
        self.count = 0

    def match(self, first, second, goals, length=90, venue="Neutral Field", day=None):
        """``first``/``second`` are ``(lineup, goal_minutes)``.

        A lineup is a list of ``(player, on, off)``. ``goals`` is the recorded
        score, which need not agree with the goal minutes — that is the case the
        reconciliation filter exists for.
        """
        self.count += 1
        game = f"g{self.count}"
        day = day or self.count
        self.conn.execute(
            "INSERT INTO games (id, series_id, section, kickoff, venue, game_over, length)"
            " VALUES (?, 's1', '1', ?, ?, 1, ?)",
            (game, "2099-04-%02d 13:00:00" % (day % 28 + 1), venue, length))
        for index, ((lineup, minutes), score) in enumerate(zip((first, second), goals)):
            side = f"{game}-{index}"
            self.conn.execute(
                "INSERT INTO game_teams (id, game_id, series_id, team_pk, score)"
                " VALUES (?, ?, 's1', ?, ?)",
                (side, game, "t-a" if index == 0 else "t-b", score))
            for player, on, off in lineup:
                self.conn.execute(
                    "INSERT INTO appearances"
                    " (game_team_id, player_id, role, on_minute, off_minute, minutes)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (side, player, "start" if on == 0 else "bench", on, off,
                     max(0, off - on)))
            for seq, minute in enumerate(minutes):
                self.conn.execute(
                    "INSERT INTO events (game_team_id, player_id, type, minute, seq)"
                    " VALUES (?, ?, 'goal', ?, ?)", (side, lineup[0][0], minute, seq))
        return game


def eleven(prefix, on=0, off=90, count=11):
    return [(f"{prefix}{index}", on, off) for index in range(count)]


class Segments(unittest.TestCase):
    def setUp(self):
        self.build = Builder()
        self.addCleanup(self.build.conn.close)

    def rows(self, **kwargs):
        return rapm.segments(self.build.conn, **kwargs)

    def test_a_match_with_no_changes_is_one_segment(self):
        self.build.match((eleven("a"), [10]), (eleven("b"), []), (1, 0))
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].minutes, 90)
        self.assertEqual(rows[0].difference, 1)
        self.assertEqual(len(rows[0].first), 11)

    def test_a_substitution_splits_the_match(self):
        lineup = eleven("a", count=10) + [("a10", 0, 60), ("a11", 60, 90)]
        self.build.match((lineup, [70]), (eleven("b"), []), (1, 0))
        rows = self.rows()
        self.assertEqual([row.minutes for row in rows], [60, 30])
        self.assertIn("a10", rows[0].first)
        self.assertNotIn("a11", rows[0].first)
        self.assertIn("a11", rows[1].first)
        self.assertEqual([row.difference for row in rows], [0, 1])

    def test_a_dismissal_leaves_ten_on_the_pitch(self):
        lineup = eleven("a", count=10) + [("a10", 0, 35)]
        self.build.match((lineup, []), (eleven("b"), [50]), (0, 1))
        rows = self.rows()
        self.assertEqual([row.minutes for row in rows], [35, 55])
        self.assertEqual(len(rows[0].first), 11)
        self.assertEqual(len(rows[1].first), 10)
        self.assertEqual(rows[1].difference, -1)

    def test_a_goal_on_a_boundary_belongs_to_the_earlier_segment(self):
        lineup = eleven("a", count=10) + [("a10", 0, 60), ("a11", 60, 90)]
        self.build.match((lineup, [60]), (eleven("b"), []), (1, 0))
        rows = self.rows()
        self.assertEqual([row.difference for row in rows], [1, 0])
        self.assertIn("a10", rows[0].first)

    def test_a_change_after_full_time_buys_nobody_minutes(self):
        lineup = eleven("a") + [("a99", 93, 90)]
        self.build.match((lineup, []), (eleven("b"), []), (0, 0))
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertNotIn("a99", rows[0].first)

    def test_an_incomplete_eleven_is_left_out(self):
        self.build.match((eleven("a", count=9), []), (eleven("b"), []), (0, 0))
        self.assertEqual(self.rows(), [])

    def test_goals_that_do_not_add_up_are_dropped(self):
        # Two events, a recorded score of three: an own goal the API stores as a
        # count rather than an event.
        self.build.match((eleven("a"), [10, 20]), (eleven("b"), []), (3, 0))
        self.assertEqual(self.rows(), [])
        self.assertEqual(len(self.rows(reconcile=False)), 1)

    def test_minutes_are_counted_for_both_sides(self):
        lineup = eleven("a", count=10) + [("a10", 0, 60), ("a11", 60, 90)]
        self.build.match((lineup, []), (eleven("b"), []), (0, 0))
        played = rapm.minutes(self.rows())
        self.assertEqual(played["a10"], 60)
        self.assertEqual(played["a11"], 30)
        self.assertEqual(played["b0"], 90)

    def test_the_home_side_is_taken_from_the_venue(self):
        for index in range(4):
            self.build.match((eleven("a"), []), (eleven("b"), []), (0, 0),
                             venue="Alpha Ground", day=index)
        rows = self.rows()
        self.assertTrue(all(row.home == 1 for row in rows))


class Solver(unittest.TestCase):
    """Conjugate gradient has to agree with the ridge solution it approximates."""

    def closed_form(self, design, penalties):
        # Small enough to build (X'X + diag(p)) and eliminate directly.
        size = design.columns
        matrix = [[penalties[i] if i == j else 0.0 for j in range(size)]
                  for i in range(size)]
        for entries in design.rows:
            for column_i, value_i in entries:
                for column_j, value_j in entries:
                    matrix[column_i][column_j] += value_i * value_j
        rhs = design.normal_rhs()
        for pivot in range(size):
            best = max(range(pivot, size), key=lambda r: abs(matrix[r][pivot]))
            matrix[pivot], matrix[best] = matrix[best], matrix[pivot]
            rhs[pivot], rhs[best] = rhs[best], rhs[pivot]
            divisor = matrix[pivot][pivot]
            for row in range(size):
                if row == pivot:
                    continue
                factor = matrix[row][pivot] / divisor
                for column in range(pivot, size):
                    matrix[row][column] -= factor * matrix[pivot][column]
                rhs[row] -= factor * rhs[pivot]
        return [rhs[index] / matrix[index][index] for index in range(size)]

    def test_conjugate_gradient_matches_the_direct_solution(self):
        rng = random.Random(7)
        players = {f"p{index}": index for index in range(6)}
        rows = []
        for index in range(40):
            first = tuple(rng.sample(sorted(players), 3))
            second = tuple(p for p in sorted(players) if p not in first)
            rows.append(rapm.Segment(f"g{index // 2}", "2099", "s1", ("100", "200"),
                                     1 if index % 2 else 0, 45,
                                     rng.choice([-1, 0, 0, 1]), first, second))
        design = rapm.Design(rows, players)
        penalties = design.penalties(2.0, 2.0)
        got = rapm.solve(design, penalties)
        want = self.closed_form(design, penalties)
        for a, b in zip(got, want):
            self.assertAlmostEqual(a, b, places=8)

    def test_an_empty_problem_solves_to_zero(self):
        design = rapm.Design([], {})
        self.assertEqual(rapm.solve(design, design.penalties()), [0.0])


class Recovery(unittest.TestCase):
    """The point of the method: separate one player from the side around them."""

    def setUp(self):
        self.build = Builder()
        self.addCleanup(self.build.conn.close)
        rng = random.Random(11)
        squad = [f"a{index}" for index in range(16)]
        for match in range(60):
            star = match % 2 == 0
            pool = [player for player in squad if player != "a0"]
            rng.shuffle(pool)
            picked = (["a0"] + pool[:10]) if star else pool[:11]
            lineup = [(player, 0, 90) for player in picked]
            minutes = [20, 55, 75] if star else []
            self.build.match((lineup, minutes), (eleven("b"), []),
                             (len(minutes), 0), day=match)
        self.rows = rapm.segments(self.build.conn)

    def test_the_planted_player_rates_highest(self):
        ratings, _, _, _ = rapm.fit(self.rows, min_minutes=90, with_clubs=False,
                                    player_penalty=1.0)
        self.assertEqual(max(ratings, key=ratings.get), "a0")
        self.assertGreater(ratings["a0"], 1.0)

    def test_teammates_are_not_credited_with_the_planted_effect(self):
        ratings, _, _, _ = rapm.fit(self.rows, min_minutes=90, with_clubs=False,
                                    player_penalty=1.0)
        others = [value for player, value in ratings.items()
                  if player.startswith("a") and player != "a0"]
        self.assertLess(max(others), ratings["a0"] / 2)

    def test_shrinkage_pulls_ratings_towards_nothing(self):
        loose, _, _, _ = rapm.fit(self.rows, min_minutes=90, with_clubs=False,
                                  player_penalty=1.0)
        tight, _, _, _ = rapm.fit(self.rows, min_minutes=90, with_clubs=False,
                                  player_penalty=500.0)
        self.assertLess(abs(tight["a0"]), abs(loose["a0"]))

    def test_a_player_below_the_minutes_floor_gets_no_column(self):
        ratings, _, _, _ = rapm.fit(self.rows, min_minutes=10 ** 6, with_clubs=False)
        self.assertEqual(ratings, {})


class Validation(unittest.TestCase):
    def test_cross_validation_reports_every_model(self):
        build = Builder()
        self.addCleanup(build.conn.close)
        rng = random.Random(3)
        for match in range(40):
            scored = rng.choice([0, 0, 1, 2])
            build.match((eleven("a"), sorted(rng.sample(range(1, 90), scored))),
                        (eleven("b"), []), (scored, 0), day=match)
        rows = rapm.segments(build.conn)
        scores, penalties = rapm.validate(rows, count=4, min_minutes=90)
        self.assertEqual(set(scores), {"zero", "clubs", "players", "clubs+players"})
        self.assertTrue(all(value >= 0 for value in scores.values()))
        self.assertEqual(set(penalties), {"clubs", "players", "clubs+players"})
        self.assertTrue(all(len(picks) == 4 for picks in penalties.values()))

    def test_without_tuning_every_fold_uses_the_same_penalties(self):
        rows = self.noisy_rows()
        _, penalties = rapm.validate(rows, count=3, min_minutes=90)
        self.assertEqual(set(penalties["clubs+players"]),
                         {(rapm.PLAYER_PENALTY, rapm.CLUB_PENALTY)})

    def test_tuning_picks_from_the_grid_and_only_sees_the_training_fold(self):
        rows = self.noisy_rows()
        seen = []
        original = rapm.tune

        def spy(train, **kwargs):
            seen.append({row.game for row in train})
            return original(train, **kwargs)

        rapm.tune = spy
        try:
            _, penalties = rapm.validate(rows, count=3, min_minutes=90, nested=True)
        finally:
            rapm.tune = original

        for picks in penalties.values():
            for player_penalty, club_penalty in picks:
                self.assertIn(player_penalty, rapm.PLAYER_PENALTIES)
                self.assertIn(club_penalty, rapm.CLUB_PENALTIES)

        # Whatever tune was shown, the fold it was choosing for was not in it.
        held = [test for _, test in rapm.folds(rows, count=3)]
        for index, games in enumerate(seen):
            self.assertFalse(games & {row.game for row in held[index % 3]})

    def test_tuning_shrinks_harder_when_there_is_no_player_effect_to_find(self):
        """The whole point of choosing the penalty: let the data set it.

        One sample has a planted player worth three goals a match, the other is
        the same shape with nobody responsible for anything. The second should
        be pulled towards zero harder than the first.
        """
        noise, _ = rapm.tune(self.noisy_rows(), count=3, min_minutes=90,
                             use_clubs=False)
        signal, _ = rapm.tune(self.planted_rows(), count=3, min_minutes=90,
                              use_clubs=False)
        self.assertGreater(noise, signal)

    def noisy_rows(self):
        build = Builder()
        self.addCleanup(build.conn.close)
        rng = random.Random(11)
        for match in range(48):
            scored = rng.choice([0, 0, 1, 2])
            build.match((eleven("a"), sorted(rng.sample(range(1, 90), scored))),
                        (eleven("b"), []), (scored, 0), day=match)
        return rapm.segments(build.conn)

    def planted_rows(self):
        """The same shape, but "a0" is worth three goals whenever they play."""
        build = Builder()
        self.addCleanup(build.conn.close)
        rng = random.Random(11)
        squad = [f"a{index}" for index in range(16)]
        for match in range(48):
            star = match % 2 == 0
            pool = [player for player in squad if player != "a0"]
            rng.shuffle(pool)
            picked = (["a0"] + pool[:10]) if star else pool[:11]
            minutes = [20, 55, 75] if star else []
            build.match(([(player, 0, 90) for player in picked], minutes),
                        (eleven("b"), []), (len(minutes), 0), day=match)
        return rapm.segments(build.conn)

    def test_the_forward_split_cuts_each_season_by_date_and_never_across(self):
        rows = [rapm.Segment(f"{year}-{index}", year, "s1", ("100", "200"), 0,
                             90, 0, ("a",), ("b",))
                for year in ("2024", "2025") for index in range(10)]
        dates = {row.game: f"{row.year}-{row.game.split('-')[1]:0>2}-01" for row in rows}
        train, test = rapm.season_split(rows, dates, share=0.6)
        for year in ("2024", "2025"):
            early = sorted(row.game for row in train if row.year == year)
            late = sorted(row.game for row in test if row.year == year)
            self.assertEqual(len(early), 6)
            self.assertEqual(len(late), 4)
            self.assertLess(max(dates[g] for g in early), min(dates[g] for g in late))

    def test_the_forward_split_scores_every_model(self):
        rows = self.planted_rows()
        dates = {row.game: f"2099-01-{int(row.game[1:]) + 1:02d}" for row in rows}
        scores, penalties = rapm.forward(rows, dates, min_minutes=90)
        self.assertEqual(set(scores), {"zero", "clubs", "players", "clubs+players"})
        self.assertLess(scores["clubs+players"], scores["zero"])
        self.assertTrue(all(len(picks) == 1 for picks in penalties.values()))

    def test_folds_keep_a_match_whole(self):
        rows = [rapm.Segment(f"g{index // 3}", "2099", "s1", ("100", "200"), 0,
                             30, 0, ("a",), ("b",)) for index in range(30)]
        for train, test in rapm.folds(rows, count=5):
            self.assertFalse({row.game for row in train} & {row.game for row in test})
            self.assertEqual(len(train) + len(test), len(rows))


if __name__ == "__main__":
    unittest.main()
