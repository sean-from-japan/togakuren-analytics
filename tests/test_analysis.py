import unittest

from togakuren import analysis, dashboard, db, ingest

from . import fixtures


class Base(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)
        ingest.ingest_series(self.conn, fixtures.TwoGameClient(), fixtures.SERIES)
        self.profile = analysis.team_profile(self.conn, "series-1")
        self.by_team = {row["team"]: row for row in self.profile}


class TeamProfile(Base):
    def test_ranked_by_points_then_goal_difference(self):
        self.assertEqual([row["rank"] for row in self.profile], [1, 2])
        self.assertEqual(self.profile[0]["points"], 3 + 0)
        self.assertEqual(self.profile[1]["points"], 0 + 3)
        self.assertEqual(self.profile[0]["goal_difference"], 1)

    def test_goals_against_come_from_the_opponent_record(self):
        self.assertEqual(self.by_team["Alpha"]["goals_for"], 2)
        self.assertEqual(self.by_team["Alpha"]["goals_against"], 1)

    def test_shots_per_game_and_conversion(self):
        alpha = self.by_team["Alpha"]
        self.assertEqual(alpha["shots"], 7 + 2)
        self.assertAlmostEqual(alpha["shots_per_game"], 9 / 2)
        self.assertAlmostEqual(alpha["conversion"], 2 / 9)

    def test_core_share_is_between_zero_and_one(self):
        for row in self.profile:
            self.assertGreater(row["core_share"], 0)
            self.assertLessEqual(row["core_share"], 1)
            self.assertAlmostEqual(row["core_share"] + row["rotation"], 1)

    def test_a_team_that_never_substitutes_has_no_rotation(self):
        # Beta fields the same eleven twice with one change, Alpha rotates more.
        self.assertGreater(self.by_team["Beta"]["core_share"], self.by_team["Alpha"]["core_share"])

    def test_academic_years_are_attached(self):
        alpha = self.by_team["Alpha"]
        self.assertEqual(set(alpha["grades"]), {"1", "2", "3", "4"})
        # Every Alpha squad member is a 2nd year in the fixture.
        self.assertGreater(alpha["grades"]["2"]["minutes"], 0)
        self.assertEqual(alpha["grades"]["4"]["minutes"], 0)
        self.assertAlmostEqual(alpha["mean_grade"], 2.0)
        self.assertAlmostEqual(alpha["youth_share"], 1.0)

    def test_goals_are_credited_to_the_scorer_year_group(self):
        self.assertEqual(self.by_team["Alpha"]["grades"]["2"]["goals"], 2)


class Fingerprints(Base):
    def test_axes_are_scaled_across_the_series(self):
        prints = analysis.fingerprints(self.conn, "series-1", self.profile)
        self.assertEqual(len(prints), 2)
        for axis, _, _ in analysis.FINGERPRINT_AXES:
            values = sorted(entry["axes"][axis] for entry in prints)
            self.assertEqual(values[0], 0.0)
            self.assertEqual(values[-1], 100.0)

    def test_identical_inputs_land_mid_scale(self):
        self.assertEqual(analysis._scale([4, 4, 4]), [50.0, 50.0, 50.0])

    def test_conceding_less_scores_higher_on_defence(self):
        prints = {entry["team"]: entry for entry in
                  analysis.fingerprints(self.conn, "series-1", self.profile)}
        conceded = {row["team"]: row["conceded_per_game"] for row in self.profile}
        best = min(conceded, key=conceded.get)
        self.assertEqual(prints[best]["axes"]["defence"], 100.0)


class Curves(Base):
    def test_points_accumulate_across_matchdays(self):
        curve = {entry["team"]: entry["points"] for entry in analysis.points_curve(self.conn, "series-1")}
        self.assertEqual(curve["Alpha"], [(1, 3), (2, 3)])
        self.assertEqual(curve["Beta"], [(1, 0), (2, 3)])

    def test_goals_split_by_opponent_half(self):
        rows = {entry["team"]: entry for entry in
                analysis.goals_by_opponent(self.conn, "series-1", self.profile)}
        for row in rows.values():
            self.assertEqual(row["vs_top"] + row["vs_bottom"],
                             self.by_team[row["team"]]["goals_for"])


class MinutesMatrix(Base):
    def test_every_matchday_and_player_is_covered(self):
        team_pk = self.by_team["Alpha"]["team_pk"]
        grid = analysis.minutes_matrix(self.conn, "series-1", team_pk)
        self.assertEqual(grid["sections"], [1, 2])
        self.assertTrue(grid["players"])
        totals = [player["total"] for player in grid["players"]]
        self.assertEqual(totals, sorted(totals, reverse=True))

    def test_squad_detail_is_joined_on(self):
        team_pk = self.by_team["Alpha"]["team_pk"]
        grid = analysis.minutes_matrix(self.conn, "series-1", team_pk)
        self.assertTrue(all(player["grade"] for player in grid["players"]))

    def test_a_player_who_missed_a_matchday_has_no_entry_for_it(self):
        team_pk = self.by_team["Alpha"]["team_pk"]
        grid = analysis.minutes_matrix(self.conn, "series-1", team_pk)
        keys = {section for player in grid["players"] for section in player["minutes"]}
        self.assertTrue(keys <= {1, 2})


class History(Base):
    def test_a_club_is_followed_by_its_federation_id(self):
        rows = analysis.team_history(self.conn, "100")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["division"], "D1")
        self.assertEqual(rows[0]["points_per_game"], 3.0)

    def test_unknown_club(self):
        self.assertEqual(analysis.team_history(self.conn, "999"), [])


class Dashboard(Base):
    def test_it_renders_with_names(self):
        html = dashboard.build(self.conn, "series-1", mode="full")
        self.assertIn("<!doctype html>", html)
        self.assertIn('charset="utf-8"', html)
        self.assertIn("Alpha", html)
        self.assertIn("Alpha Player 1", html)

    def test_aggregate_mode_drops_every_squad_view(self):
        html = dashboard.build(self.conn, "series-1", mode="aggregate")
        self.assertNotIn("Alpha Player", html)
        self.assertNotIn("出場時間マトリクス", html)
        self.assertIn("Alpha", html)

    def test_payload_cannot_close_the_script_element(self):
        html = dashboard.build(self.conn, "series-1", mode="full")
        payload = html.split('id="payload"', 1)[1].split("</script>", 1)[0]
        self.assertNotIn("<", payload.split(">", 1)[1])

    def test_unknown_series(self):
        with self.assertRaises(ValueError):
            dashboard.build(self.conn, "nope")
