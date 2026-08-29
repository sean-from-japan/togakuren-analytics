"""End to end: fake API payloads through ingest, metrics, report and CLI."""

import io
import unittest
from contextlib import redirect_stderr

from togakuren import cli, db, ingest, metrics, report

from . import fixtures


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)
        ingest.ingest_series(self.conn, fixtures.FakeClient(), fixtures.SERIES)

    def test_every_table_is_populated(self):
        counts = db.counts(self.conn)
        self.assertEqual(counts["games"], 1)
        self.assertEqual(counts["game_teams"], 2)
        self.assertEqual(counts["teams"], 2)
        self.assertEqual(counts["players"], 28)
        self.assertGreater(counts["appearances"], 20)

    def test_ingesting_twice_does_not_duplicate(self):
        before = db.counts(self.conn)
        ingest.ingest_series(self.conn, fixtures.FakeClient(), fixtures.SERIES)
        self.assertEqual(db.counts(self.conn), before)

    def test_player_rates_are_derived_from_reconstructed_minutes(self):
        rows = {row["player_id"]: row for row in
                metrics.player_season(self.conn, "series-1", min_minutes=0)}
        self.assertEqual(rows["a2"]["minutes"], 70)
        self.assertEqual(rows["a2"]["shots"], 3)
        self.assertAlmostEqual(rows["a2"]["shots_per_90"], round(3 * 90 / 70, 2))

    def test_substitute_appearances_are_counted_separately(self):
        rows = {row["player_id"]: row for row in
                metrics.player_season(self.conn, "series-1", min_minutes=0)}
        self.assertEqual((rows["a13"]["starts"], rows["a13"]["sub_apps"]), (0, 1))

    def test_min_minutes_filters_small_samples(self):
        self.assertEqual(metrics.player_season(self.conn, "series-1", min_minutes=80), [
            row for row in metrics.player_season(self.conn, "series-1", min_minutes=80)
        ])
        self.assertTrue(
            all(row["minutes"] >= 80
                for row in metrics.player_season(self.conn, "series-1", min_minutes=80))
        )

    def test_team_totals(self):
        rows = {row["team"]: row for row in metrics.team_season(self.conn, "series-1")}
        self.assertEqual(rows["Alpha"]["shots"], 7)
        self.assertEqual(rows["Alpha"]["goals_for"], 2)
        self.assertEqual(rows["Alpha"]["points"], 3)

    def test_shot_periods_and_goal_timeline(self):
        self.assertEqual(metrics.shot_periods(self.conn, "series-1"), [4, 5, 0, 0])
        timeline = dict(metrics.goal_minutes(self.conn, "series-1"))
        self.assertEqual(timeline[0], 1)
        self.assertEqual(timeline[75], 1, "a 90+2 goal belongs to the final block")

    def test_dropping_personal_data_keeps_the_analysis_working(self):
        db.drop_personal_data(self.conn)
        counts = db.counts(self.conn)
        self.assertEqual(counts["players"], 0)
        self.assertEqual(counts["squad_members"], 0)
        rows = metrics.player_season(self.conn, "series-1", min_minutes=0)
        self.assertTrue(rows)
        self.assertTrue(all(row["team"] for row in rows))
        self.assertTrue(any(row["position"] for row in rows),
                        "positions survive via the appearance records")

    def test_manager_name_is_cleared_with_the_rest(self):
        db.drop_personal_data(self.conn)
        managers = [row[0] for row in self.conn.execute("SELECT manager FROM game_teams")]
        self.assertEqual(set(managers), {None})


class Report(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)
        ingest.ingest_series(self.conn, fixtures.FakeClient(), fixtures.SERIES)

    def test_full_report_names_players(self):
        html = report.build(self.conn, "series-1", mode="full", min_minutes=0)
        self.assertIn("Alpha Player 1", html)
        self.assertIn("<!doctype html>", html)
        self.assertIn('charset="utf-8"', html)
        self.assertIn("viewport", html)

    def test_aggregate_report_contains_no_person(self):
        html = report.build(self.conn, "series-1", mode="aggregate", min_minutes=0)
        self.assertNotIn("Alpha Player", html)
        self.assertNotIn("Beta Player", html)
        self.assertIn("Alpha", html, "team level figures remain")

    def test_pseudonymous_report_warns_about_residual_risk(self):
        html = report.build(
            self.conn, "series-1", mode="pseudonym", salt="a" * 32, min_minutes=0
        )
        self.assertNotIn("Alpha Player", html)
        self.assertIn("pseudonymised, not anonymous", html)

    def test_unknown_series(self):
        with self.assertRaises(ValueError):
            report.build(self.conn, "nope")


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)

    def test_parser_requires_a_command(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.build_parser().parse_args([])

    def test_local_views_default_to_full_and_export_to_pseudonym(self):
        parser = cli.build_parser()
        self.assertEqual(parser.parse_args(["report"]).privacy, "full")
        self.assertEqual(parser.parse_args(["dashboard"]).privacy, "full")
        self.assertEqual(parser.parse_args(["export"]).privacy, "pseudonym")

    def test_series_can_be_resolved_by_search_term(self):
        ingest.ingest_series(self.conn, fixtures.FakeClient(), fixtures.SERIES)
        self.assertEqual(cli._resolve_series(self.conn, "latest"), "series-1")
        self.assertEqual(cli._resolve_series(self.conn, "Division 1"), "series-1")
        self.assertEqual(cli._resolve_series(self.conn, "series-1"), "series-1")

    def test_every_term_must_match(self):
        ingest.ingest_series(self.conn, fixtures.FakeClient(), fixtures.SERIES)
        self.assertEqual(cli._resolve_series(self.conn, "2099 Division"), "series-1")
        with self.assertRaises(SystemExit):
            cli._resolve_series(self.conn, "2099 Bundesliga")

    def test_unknown_series_term_exits(self):
        ingest.ingest_series(self.conn, fixtures.FakeClient(), fixtures.SERIES)
        with self.assertRaises(SystemExit):
            cli._resolve_series(self.conn, "Bundesliga")

    def test_empty_database_exits(self):
        with self.assertRaises(SystemExit):
            cli._resolve_series(self.conn, "latest")
