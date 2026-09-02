"""Every command run end to end, against a database built from the fixtures.

The command layer was the second least covered module here, which is awkward for
a tool whose entire interface is the command line: the analysis was tested and
the way anybody actually reaches it was not. Each test below goes through
``cli.main`` — argument parsing, the command body, and the output — so a command
that raises on a real invocation cannot pass.

No network: ``_client`` is replaced with the fixture client.
"""
import contextlib
import io
import logging
import pathlib
import re
import tempfile
import unittest
from unittest import mock

from togakuren import cli, db, ingest, paths

from . import fixtures


def seeded(path, client=None):
    """A database at ``path`` holding the fixture season."""
    conn = db.connect(path)
    ingest.ingest_series(conn, client or fixtures.TwoGameClient(), fixtures.SERIES)
    conn.close()


class Command(unittest.TestCase):
    """Base: a temporary database, a temporary working directory, no network."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = pathlib.Path(self.directory.name)
        self.db = self.root / "test.sqlite3"
        # cli.main configures logging; the ingest progress lines are not the
        # subject of these tests and would drown the runner's own output.
        logging.disable(logging.INFO)
        self.addCleanup(logging.disable, logging.NOTSET)
        seeded(self.db)
        patch = mock.patch.object(cli, "_client",
                                  lambda args: fixtures.TwoGameClient())
        patch.start()
        self.addCleanup(patch.stop)

    def run_cli(self, *argv):
        """Run one command, returning what it printed."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["--db", str(self.db), *argv]), 0)
        return out.getvalue()


class Listing(Command):
    def test_list_names_the_loaded_series(self):
        self.assertIn("Example League 2099", self.run_cli("list"))

    def test_series_lists_what_the_federation_offers(self):
        self.assertIn("2099", self.run_cli("series"))

    def test_ingest_reports_what_it_loaded(self):
        fresh = self.root / "fresh.sqlite3"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["--db", str(fresh), "ingest", "--year", "2099"])
        self.assertTrue(fresh.exists())

    def test_version_is_reported(self):
        from togakuren import __version__
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            cli.main(["--version"])
        self.assertIn(__version__, out.getvalue())


class Analysis(Command):
    def test_profiles_writes_a_markdown_document(self):
        target = self.root / "season.md"
        self.run_cli("profiles", "--series", "latest", "--out", str(target))
        self.assertIn("Example League", target.read_text(encoding="utf-8"))

    def test_profiles_writes_japanese_too(self):
        target = self.root / "season.ja.md"
        self.run_cli("profiles", "--series", "latest", "--lang", "ja",
                     "--out", str(target))
        self.assertTrue(target.read_text(encoding="utf-8").strip())

    def test_a_profile_document_names_no_player(self):
        target = self.root / "season.md"
        self.run_cli("profiles", "--series", "latest", "--out", str(target))
        self.assertNotIn("Alpha Player 1", target.read_text(encoding="utf-8"))

    def test_trends_writes_a_cross_season_page(self):
        target = self.root / "trends.html"
        self.run_cli("trends", "--out", str(target))
        self.assertIn("<html", target.read_text(encoding="utf-8").lower())

    def test_trends_can_emit_markdown(self):
        target = self.root / "trends.md"
        self.run_cli("trends", "--format", "md", "--out", str(target))
        self.assertTrue(target.read_text(encoding="utf-8").strip())

    def test_sample_runs_on_invented_data(self):
        target = self.root / "sample.md"
        self.run_cli("sample", "--out", str(target))
        self.assertTrue(target.read_text(encoding="utf-8").strip())


class Views(Command):
    def test_report_writes_html(self):
        target = self.root / "report.html"
        self.run_cli("report", "--out", str(target))
        text = target.read_text(encoding="utf-8")
        self.assertIn("<html", text.lower())

    def test_dashboard_writes_html(self):
        target = self.root / "dashboard.html"
        self.run_cli("dashboard", "--out", str(target))
        self.assertIn("<html", target.read_text(encoding="utf-8").lower())

    def test_an_aggregate_report_carries_no_player_name(self):
        target = self.root / "aggregate.html"
        self.run_cli("report", "--out", str(target), "--privacy", "aggregate")
        text = target.read_text(encoding="utf-8")
        self.assertNotIn("Alpha Player 1", text)

    def test_public_refuses_to_write_real_names(self):
        target = self.root / "refused.html"
        with self.assertRaises(SystemExit):
            cli.main(["--db", str(self.db), "report", "--out", str(target),
                      "--privacy", "full", "--public"])


class Export(Command):
    def test_export_to_stdout_is_csv(self):
        output = self.run_cli("export", "--min-minutes", "0")
        self.assertIn(",", output.splitlines()[0])

    def test_export_to_a_file(self):
        target = self.root / "rows.csv"
        self.run_cli("export", "--out", str(target), "--min-minutes", "0")
        self.assertTrue(target.read_text(encoding="utf-8").strip())

    def test_export_defaults_to_pseudonyms_and_hides_real_names(self):
        output = self.run_cli("export", "--min-minutes", "0")
        self.assertNotIn("Alpha Player 1", output)

    def test_privacy_check_reports_a_uniqueness_figure(self):
        output = self.run_cli("privacy-check", "--min-minutes", "0")
        self.assertRegex(output, r"\d")


class Models(Command):
    """The model commands, on a database far too small to say anything.

    These prove the commands run and degrade gracefully, not that a number is
    right: three fixtures cannot support a forecast and should not pretend to.
    The figures are checked in test_predict and test_rapm instead.
    """

    def test_forecast_says_so_when_there_is_nothing_left_to_play(self):
        with self.assertRaises(SystemExit) as exit_:
            cli.main(["--db", str(self.db), "forecast", "--series", "latest"])
        self.assertIn("played", str(exit_.exception))

    def test_backtest_runs(self):
        self.run_cli("backtest")

    def test_ratings_runs(self):
        self.run_cli("ratings")

    def test_ratings_validate_runs(self):
        self.run_cli("ratings", "--validate")

    def test_ratings_forward_explains_a_sample_it_cannot_split(self):
        """Three fixtures cannot be cut 60/40 inside a season; say so plainly."""
        with contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaises(SystemExit) as exit_:
            cli.main(["--db", str(self.db), "ratings", "--forward"])
        self.assertIn("cannot split", str(exit_.exception))


class Forecasting(Command):
    """A season with a fixture still to come, which is what forecast is for."""

    def setUp(self):
        super().setUp()
        self.db = self.root / "unfinished.sqlite3"
        conn = db.connect(self.db)
        ingest.ingest_series(conn, fixtures.UnfinishedSeasonClient(), fixtures.SERIES)
        conn.close()

    def test_forecast_prints_a_row_per_remaining_fixture(self):
        output = self.run_cli("forecast", "--series", "latest", "--runs", "50")
        self.assertIn("fixtures to play", output)
        self.assertIn("2099-04-15", output)

    def test_the_three_probabilities_are_shown_for_each_fixture(self):
        output = self.run_cli("forecast", "--series", "latest", "--runs", "50")
        row = [line for line in output.splitlines() if "2099-04-15" in line][0]
        self.assertGreaterEqual(len(re.findall(r"\d+\.\d", row)), 3)

    def test_the_simulated_table_names_the_clubs(self):
        output = self.run_cli("forecast", "--series", "latest", "--runs", "50")
        self.assertIn("Alpha", output)
        self.assertIn("Beta", output)


class Failures(Command):
    def test_an_unknown_series_exits_rather_than_traces(self):
        with self.assertRaises(SystemExit):
            cli.main(["--db", str(self.db), "report", "--series", "Bundesliga"])

    def test_an_empty_database_exits_rather_than_reporting_on_nothing(self):
        empty = self.root / "empty.sqlite3"
        db.connect(empty).close()
        with self.assertRaises(SystemExit):
            cli.main(["--db", str(empty), "report",
                      "--out", str(self.root / "none.html")])

    def test_an_api_error_becomes_a_message_not_a_traceback(self):
        from togakuren.client import ApiError

        def angry(args):
            raise ApiError("the site is down")

        with mock.patch.object(cli, "_client", angry), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exit_:
                cli.main(["--db", str(self.db), "series"])
        self.assertIn("the site is down", str(exit_.exception))


class Defaults(unittest.TestCase):
    def test_the_database_default_is_outside_the_working_directory(self):
        """A path inside the repository would be one `git add .` from a leak."""
        self.assertNotIn(pathlib.Path.cwd(), paths.database().parents)

    def test_the_package_version_matches_pyproject(self):
        from togakuren import __version__
        text = (pathlib.Path(__file__).resolve().parent.parent
                / "pyproject.toml").read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("version"):
                self.assertEqual(line.split("=")[1].strip().strip('"'), __version__)
                break
        else:
            self.fail("pyproject.toml has no version")


if __name__ == "__main__":
    unittest.main()
