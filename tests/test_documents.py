"""The generated Markdown documents, and the synthetic season behind one of them."""

import unittest

from togakuren import analysis, db, ingest, markdown, metrics, sample

from . import fixtures


class SyntheticSeason(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.series_id = sample.generate(self.conn, seed=1)

    def test_it_produces_a_full_season(self):
        counts = db.counts(self.conn)
        self.assertEqual(counts["teams"], len(sample.CLUBS))
        self.assertEqual(counts["games"], sample.ROUNDS * len(sample.CLUBS) // 2)
        self.assertGreater(counts["appearances"], 1000)
        self.assertEqual(counts["standings"], len(sample.CLUBS))

    def test_points_agree_with_the_scorelines(self):
        for row in analysis.team_profile(self.conn, self.series_id):
            self.assertEqual(row["points"], row["win"] * 3 + row["draw"])
            self.assertEqual(row["played"], row["win"] + row["draw"] + row["lose"])

    def test_the_same_seed_gives_the_same_season(self):
        other = db.connect(":memory:")
        self.addCleanup(other.close)
        sample.generate(other, seed=1)
        self.assertEqual(
            [dict(r) for r in self.conn.execute("SELECT * FROM standings ORDER BY team_pk")],
            [dict(r) for r in other.execute("SELECT * FROM standings ORDER BY team_pk")],
        )

    def test_different_seeds_give_different_seasons(self):
        other = db.connect(":memory:")
        self.addCleanup(other.close)
        sample.generate(other, seed=2)
        self.assertNotEqual(
            [r[0] for r in self.conn.execute("SELECT points FROM standings ORDER BY team_pk")],
            [r[0] for r in other.execute("SELECT points FROM standings ORDER BY team_pk")],
        )

    def test_it_looks_like_a_league_rather_than_noise(self):
        profile = analysis.team_profile(self.conn, self.series_id)
        goals_per_game = sum(row["goals_for"] for row in profile) / (
            sum(row["played"] for row in profile) / 2
        )
        self.assertTrue(1.5 < goals_per_game < 6.0, goals_per_game)
        for row in profile:
            self.assertTrue(0.4 < row["core_share"] <= 1.0, row["core_share"])

    def test_no_real_federation_data_is_reachable_from_it(self):
        names = [row[0] for row in self.conn.execute("SELECT name FROM players")]
        self.assertTrue(names)
        self.assertTrue(all(name.isascii() for name in names))


class TeamProfileDocument(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)
        ingest.ingest_series(self.conn, fixtures.TwoGameClient(), fixtures.SERIES)

    def test_it_names_every_club_and_no_person(self):
        text = markdown.team_profiles(self.conn, "series-1")
        self.assertIn("Alpha", text)
        self.assertIn("Beta", text)
        names = [row[0] for row in self.conn.execute("SELECT name FROM players")]
        self.assertTrue(names)
        for name in names:
            self.assertNotIn(name, text)

    def test_both_languages_render(self):
        for lang in markdown.LABELS:
            text = markdown.team_profiles(self.conn, "series-1", lang=lang)
            self.assertIn("Alpha", text)
            self.assertIn("|", text)

    def test_a_season_in_progress_says_so(self):
        self.conn.execute("UPDATE games SET game_over = 0 WHERE id = 'game-2'")
        self.conn.commit()
        self.assertIn("1 of 2", markdown.team_profiles(self.conn, "series-1"))

    def test_unknown_series(self):
        with self.assertRaises(ValueError):
            markdown.team_profiles(self.conn, "nope")


class PlayerDocument(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.series_id = sample.generate(self.conn, seed=3)

    def test_it_names_the_invented_players(self):
        text = markdown.player_document(self.conn, self.series_id, min_minutes=0, top=5)
        rows = metrics.player_season(self.conn, self.series_id, min_minutes=0)
        names = dict(self.conn.execute("SELECT player_id, name FROM players"))
        self.assertIn(names[rows[0]["player_id"]], text)

    def test_it_states_that_the_data_is_invented(self):
        for lang, needle in (("en", "invented"), ("ja", "架空")):
            self.assertIn(needle, markdown.player_document(self.conn, self.series_id, lang=lang))

    def test_the_minutes_grid_has_a_column_per_matchday(self):
        text = markdown.player_document(self.conn, self.series_id)
        self.assertIn("Minutes by matchday", text)
        header = next(line for line in text.splitlines() if line.startswith("| Player | Yr | Pos |"))
        self.assertEqual(header.count("|"), 3 + sample.ROUNDS + 2)
