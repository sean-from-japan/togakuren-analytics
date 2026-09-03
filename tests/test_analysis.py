import unittest

from togakuren import analysis, dashboard, db, ingest, trends

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
        self.assertEqual(rows[0]["division"], "1部リーグ")
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


class Seasons(Base):
    def test_summary_reports_scale_and_scoring(self):
        rows = analysis.season_summary(self.conn)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["teams"], 2)
        self.assertEqual(row["games"], 2)
        self.assertEqual(row["goals"], 3)
        self.assertAlmostEqual(row["goals_per_game"], 1.5)
        self.assertEqual(row["complete"], 1.0)
        self.assertTrue(row["has_player_data"])

    def test_per_minute_columns_are_withheld_without_lineups(self):
        self.conn.execute("DELETE FROM appearances")
        self.conn.commit()
        row = analysis.season_summary(self.conn)[0]
        self.assertFalse(row["has_player_data"])
        self.assertIsNone(row["shots_per_game"])
        self.assertIsNone(row["conversion"])
        # A results-only season still reports what it does have.
        self.assertAlmostEqual(row["goals_per_game"], 1.5)

    def test_grade_trend_shares_sum_to_one(self):
        rows = analysis.grade_trend(self.conn)
        self.assertTrue(rows)
        self.assertAlmostEqual(sum(row["minutes_share"] for row in rows), 1.0, places=6)

    def test_grade_trend_skips_seasons_without_lineups(self):
        self.conn.execute("DELETE FROM appearances")
        self.conn.commit()
        self.assertEqual(analysis.grade_trend(self.conn), [])


class SeasonLadder(unittest.TestCase):
    """The Challenge League's level depends on which divisions ran that year."""

    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)

    def _season(self, year, divisions, club_in=None, points=10):
        """A season of empty divisions, optionally with one club standing in one."""
        for index, division in enumerate(divisions):
            sid = f"{year}-{index}"
            self.conn.executescript(
                f"""
                INSERT INTO series (id, year, name, short_name, type)
                  VALUES ('{sid}', '{year}', 'League {year} {division}',
                          '{division}', 'league');
                INSERT INTO games (id, series_id, section, kickoff, game_over, length)
                  VALUES ('{sid}-g', '{sid}', '1', '{year}-04-01', 1, 90);
                """
            )
            if division == club_in:
                self.conn.executescript(
                    f"""
                    INSERT INTO teams (id, series_id, team_id, name, short_name)
                      VALUES ('{sid}-t', '{sid}', '100', 'Alpha University FC', 'Alpha');
                    INSERT INTO standings (team_pk, series_id, played, win, draw, lose,
                                           points, goals_for, goal_difference, fairplay_points)
                      VALUES ('{sid}-t', '{sid}', 10, 3, 1, 6, {points}, 9, -5, 0);
                    """
                )
        self.conn.commit()

    def test_challenge_sits_below_the_deepest_numbered_division(self):
        # 2022-2024: first, second, Challenge. Challenge is the third level.
        self._season("2022", ["1部リーグ", "2部リーグ", "チャレンジリーグ"])
        # 2025: a third division was inserted above it, so it becomes the fourth.
        self._season("2025", ["1部リーグ", "2部リーグ", "3部リーグ", "チャレンジリーグ"])
        ladder = analysis.season_ladder(self.conn)
        self.assertEqual(ladder["2022"]["チャレンジリーグ"], 3)
        self.assertEqual(ladder["2025"]["チャレンジリーグ"], 4)

    def test_numbered_divisions_keep_their_number(self):
        self._season("2021", ["1部リーグ", "2部リーグ", "3部リーグ", "4部リーグ"])
        self._season("2026", ["1部リーグ", "2部リーグ", "3部リーグ"])
        ladder = analysis.season_ladder(self.conn)
        self.assertEqual(ladder["2021"], {"1部リーグ": 1, "2部リーグ": 2, "3部リーグ": 3, "4部リーグ": 4})
        self.assertEqual(ladder["2026"], {"1部リーグ": 1, "2部リーグ": 2, "3部リーグ": 3})

    def test_a_club_the_ladder_moved_under_is_flagged(self):
        # The 2025 reorganisation pushed the Challenge League a level down. Its
        # clubs lost a level without changing division or playing a match, and
        # the headline promotion and relegation averages leave them out.
        self._season("2024", ["1部リーグ", "2部リーグ", "チャレンジリーグ"],
                     club_in="チャレンジリーグ", points=10)
        self._season("2025", ["1部リーグ", "2部リーグ", "3部リーグ", "チャレンジリーグ"],
                     club_in="チャレンジリーグ", points=20)
        moves = analysis.division_moves(self.conn)
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0]["direction"], "relegated")
        self.assertFalse(moves[0]["moved"])

    def test_a_club_that_changes_division_is_flagged_as_moved(self):
        self._season("2024", ["1部リーグ", "2部リーグ", "チャレンジリーグ"],
                     club_in="2部リーグ", points=20)
        self._season("2025", ["1部リーグ", "2部リーグ", "3部リーグ", "チャレンジリーグ"],
                     club_in="1部リーグ", points=10)
        moves = analysis.division_moves(self.conn)
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0]["direction"], "promoted")
        self.assertTrue(moves[0]["moved"])

    def test_a_division_outside_the_ladder_has_no_level(self):
        self._season("2022", ["1部リーグ", "特別リーグ"])
        self.assertNotIn("特別リーグ", analysis.season_ladder(self.conn)["2022"])


class Trajectories(Base):
    def _add_second_season(self, division, points, played=10):
        """A follow-up season for Alpha, one tier up."""
        self.conn.executescript(
            f"""
            INSERT INTO series (id, year, name, short_name, type)
              VALUES ('series-2', '2100', 'Example League 2100 {division}', '{division}', 'league');
            INSERT INTO teams (id, series_id, team_id, name, short_name)
              VALUES ('team-a2', 'series-2', '100', 'Alpha University FC', 'Alpha');
            INSERT INTO games (id, series_id, section, kickoff, game_over, length)
              VALUES ('game-3', 'series-2', '1', '2100-04-01', 1, 90);
            INSERT INTO standings (team_pk, series_id, played, win, draw, lose, points,
                                   goals_for, goal_difference, fairplay_points)
              VALUES ('team-a2', 'series-2', {played}, 3, 1, 6, {points}, 9, -5, 0);
            """
        )
        self.conn.commit()

    def test_a_club_is_followed_by_federation_id(self):
        self._add_second_season("2部リーグ", 10)
        clubs = {club["team_id"]: club for club in analysis.club_trajectories(self.conn)}
        self.assertEqual([s["year"] for s in clubs["100"]["seasons"]], ["2099", "2100"])

    def test_a_tier_change_is_reported_as_a_move(self):
        self._add_second_season("2部リーグ", 10)
        moves = analysis.division_moves(self.conn)
        self.assertEqual(len(moves), 1)
        move = moves[0]
        self.assertEqual(move["direction"], "relegated")
        self.assertEqual(move["gap"], 1)
        self.assertAlmostEqual(move["ppg_after"], 1.0)
        self.assertAlmostEqual(move["delta"], move["ppg_after"] - move["ppg_before"])

    def test_staying_in_the_same_tier_is_not_a_move(self):
        self._add_second_season("1部リーグ", 10)
        self.assertEqual(analysis.division_moves(self.conn), [])

    def test_an_unrecognised_division_is_not_a_promotion(self):
        # A renamed or one-off competition has no place in the tier order, and
        # must not be reported as movement in either direction.
        self._add_second_season("特別リーグ", 10)
        self.assertEqual(analysis.division_moves(self.conn), [])


class Trends(Base):
    def test_it_renders_without_any_personal_data(self):
        html = trends.build(self.conn)
        self.assertIn("<!doctype html>", html)
        self.assertIn('charset="utf-8"', html)
        self.assertIn("Alpha", html)
        self.assertNotIn("Alpha Player", html)
        self.assertNotIn("Beta Player", html)

    def test_the_focus_club_is_preselected(self):
        html = trends.build(self.conn, focus_team_id="200")
        self.assertIn('value="200" selected', html)

    def test_empty_database(self):
        empty = db.connect(":memory:")
        self.addCleanup(empty.close)
        with self.assertRaises(ValueError):
            trends.build(empty)
