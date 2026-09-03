"""Origin parsing and the preseason model.

The parser tests use spelling variations that actually occur in the federation's
squad lists — the same school written four ways is the whole reason the module
exists — but no real person appears here, and the model tests run on invented
club-seasons.
"""

import unittest

from togakuren import db, intake, origins

from . import fixtures


class OriginParsing(unittest.TestCase):
    def test_place_before_the_authority_comes_off(self):
        self.assertEqual(origins.normalise_school("船橋市立船橋高校"), "市立船橋高校")
        self.assertEqual(origins.normalise_school("東京都立本所高等学校"), "都立本所高校")
        self.assertEqual(origins.normalise_school("川崎市立橘高校"),
                         origins.normalise_school("市立橘高等学校"))

    def test_the_authority_itself_stays(self):
        """The bug this module was rewritten for.

        Stripping 市立/県立 merges a national power with an academic school in
        the same city, and the merged entry led the school ranking.
        """
        self.assertNotEqual(origins.normalise_school("市立船橋高校"),
                            origins.normalise_school("県立船橋高校"))

    def test_a_name_that_ends_at_the_authority_is_left_alone(self):
        self.assertEqual(origins.normalise_school("富士市立高等学校"), "富士市立高校")

    def test_kunitachi_is_a_place_not_a_founding_authority(self):
        self.assertEqual(origins.normalise_school("国立高校"), "国立高校")
        self.assertEqual(origins.normalise_school("国立競技高校"), "競技高校")

    def test_a_bare_school_is_a_school(self):
        self.assertEqual(origins.split_origin("静岡学園高校"), (None, "静岡学園高校"))

    def test_a_club_side_is_a_club(self):
        club, school = origins.split_origin("FC東京U-18")
        self.assertEqual(club, "FC東京U-18")
        self.assertIsNone(school)

    def test_brackets_hold_the_school_the_player_attended(self):
        for raw in ("FCトリプレッタユース（都立北園高校）", "FCトリプレッタユース(都立北園高校)"):
            club, school = origins.split_origin(raw)
            self.assertEqual(club, "FCトリプレッタユース")
            self.assertEqual(school, "都立北園高校")

    def test_the_same_name_typed_twice_is_not_a_club(self):
        self.assertEqual(origins.split_origin("多摩大学目黒高校(多摩大学目黒高校)"),
                         (None, "多摩大学目黒高校"))

    def test_an_empty_value_parses_to_nothing(self):
        self.assertEqual(origins.split_origin(None), (None, None))
        self.assertEqual(origins.split_origin("   "), (None, None))

    def test_old_forms_meet_the_external_list(self):
        self.assertEqual(origins.match_key("國學院大學久我山高等学校"),
                         origins.match_key("国学院久我山"))

    def test_long_and_short_school_names_meet(self):
        self.assertEqual(origins.match_key("日本大学藤沢高校"), origins.match_key("日大藤沢"))
        self.assertEqual(origins.match_key("流通経済大学付属柏高校"),
                         origins.match_key("流通経済大柏"))


class ChampionshipReference(unittest.TestCase):
    def test_the_shipped_list_loads_and_covers_eight_editions(self):
        editions = intake.championship_editions()
        self.assertGreater(len(editions), 100)
        self.assertLessEqual(max(editions.values()), 8)
        self.assertGreaterEqual(min(editions.values()), 1)

    def test_a_perennial_qualifier_is_matched_from_the_squad_list_spelling(self):
        editions = intake.championship_editions()
        self.assertEqual(editions[origins.match_key("青森山田高校")], 8)


def _club_seasons():
    """Four seasons where the squad list carries the signal and the table does not.

    ``previous`` is deliberately uncorrelated with the outcome, so a model that
    only reads last season's table cannot beat the baseline and a model that
    reads the squad list must.
    """
    rows = []
    for year in ("2001", "2002", "2003", "2004"):
        for index in range(10):
            pedigree = (index - 4.5) / 3.0
            rows.append({
                "year": year, "club": f"club-{index}", "name": f"Club {index}", "level": 1,
                "result": pedigree + (0.1 if index % 2 else -0.1),
                "pedigree_z": pedigree, "youth_z": pedigree / 2,
                "previous": (index % 3) - 1,
                "step": 0,
                "champions": index / 10, "youth": index / 20, "pedigree": index / 4,
            })
    return rows


class Model(unittest.TestCase):
    def test_least_squares_recovers_a_line_it_was_given(self):
        rows = [{"result": 3 + 2 * x, "x": x} for x in range(-4, 5)]
        intercept, slope = intake.fit(rows, ["x"])
        self.assertAlmostEqual(intercept, 3.0, places=6)
        self.assertAlmostEqual(slope, 2.0, places=6)

    def test_correlation_of_a_series_with_itself_is_one(self):
        values = [1.0, 4.0, 2.0, 8.0]
        self.assertAlmostEqual(intake.correlation(values, values), 1.0, places=9)
        self.assertAlmostEqual(intake.correlation(values, [-v for v in values]), -1.0, places=9)

    def test_a_flat_group_standardises_to_zeros_rather_than_dividing_by_zero(self):
        self.assertEqual(intake._standardise([2.0, 2.0, 2.0]), [0.0, 0.0, 0.0])

    def test_the_squad_list_beats_a_table_that_carries_nothing(self):
        rows = _club_seasons()
        table = intake.leave_one_season_out(rows, ["previous"])
        squad = intake.leave_one_season_out(rows, ["pedigree_z"])
        self.assertLess(squad["rmse"], table["rmse"])
        self.assertGreater(squad["gain"], 0.5)

    def test_scoring_skips_clubs_missing_a_feature(self):
        rows = _club_seasons()
        for row in rows[:5]:
            del row["previous"]
        scored = intake.leave_one_season_out(rows, ["previous"])
        self.assertEqual(scored["n"], len(rows) - 5)

    def test_a_ranking_never_sees_the_season_it_ranks(self):
        rows = _club_seasons()
        target = [r for r in rows if r["year"] == "2004"]
        for row in target:            # make the held-out season the wrong way round
            row["result"] = -row["result"]
        ranked = intake.preseason_table(rows, "2004", level=1)
        self.assertEqual(len(ranked), len(target))
        self.assertLess(
            intake.correlation([r["predicted"] for r in ranked],
                               [r["result"] for r in ranked]),
            0,
        )

    def test_a_ranking_with_no_training_seasons_is_empty_rather_than_wrong(self):
        rows = [r for r in _club_seasons() if r["year"] == "2001"]
        self.assertEqual(intake.preseason_table(rows, "2001", level=1), [])


class AgainstADatabase(unittest.TestCase):
    def setUp(self):
        self.conn = fixtures.seed_seasons(db.connect(":memory:"))
        self.addCleanup(self.conn.close)
        self.rows = intake.squad_rows(self.conn)

    def test_one_row_per_club_season_with_a_table(self):
        self.assertEqual(len(self.rows), 3 * 2 * 6)
        self.assertTrue(all("pedigree_z" in row for row in self.rows))

    def test_the_first_season_has_no_previous_one(self):
        first = [row for row in self.rows if row["year"] == "2001"]
        self.assertTrue(all("previous" not in row for row in first))
        later = [row for row in self.rows if row["year"] != "2001"]
        self.assertTrue(all("previous" in row for row in later))

    def test_the_reference_list_reaches_the_squad_rows(self):
        self.assertGreater(max(row["pedigree"] for row in self.rows), 0)
        self.assertEqual(min(row["pedigree"] for row in self.rows), 0)

    def test_the_planted_signal_is_recovered_out_of_sample(self):
        scored = intake.evaluate(self.rows)
        squad = next(m for m in scored["every_club"]
                     if m["features"] == ["pedigree_z"])
        self.assertGreater(squad["gain"], 0.5)

    def test_the_split_by_move_covers_the_clubs_that_stayed(self):
        moves = {row["move"]: row for row in intake.by_move(self.rows)}
        self.assertIn("stayed", moves)
        self.assertEqual(moves["stayed"]["n"], 2 * 6 * 2)

    def test_pedigree_orders_the_divisions_it_was_never_told_about(self):
        by_level = {}
        for row in intake.division_pedigree(self.rows):
            by_level.setdefault(row["level"], []).append(row["champions"])
        self.assertEqual(sorted(by_level), [1, 2])

    def test_a_ranking_comes_back_sorted_and_complete(self):
        table = intake.preseason_table(self.rows, "2003", level=1)
        self.assertEqual(len(table), 6)
        self.assertEqual([r["predicted"] for r in table],
                         sorted((r["predicted"] for r in table), reverse=True))


if __name__ == "__main__":
    unittest.main()
