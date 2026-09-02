"""The API client, exercised without touching the network.

Every test here replaces ``urllib.request.urlopen`` with a stub. The client was
the least covered module in the package and it is the one that decides what gets
sent to somebody else's server, so the retry rule, the throttle and the token
discovery are all pinned down rather than trusted.
"""
import io
import json
import logging
import unittest
import urllib.error
from unittest import mock

from togakuren import __version__
from togakuren.client import API, USER_AGENT, ApiError, Client

#: A stand-in for the site's common.js. The token is counted hex digits, not a
#: credential -- there is no real token anywhere in this repository, by design,
#: because the client reads the live one out of the site at run time. Secret
#: scanners will flag the line; this comment is here so triage takes a second.
COMMON_JS = """
  axios.defaults.baseURL = "https://data.example.test/";
  axios.defaults.headers.common.Authorization = "Bearer 0123456789abcdef";
"""


class Response(io.BytesIO):
    """Enough of an HTTP response for ``with urlopen(...) as r: r.read()``."""

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        return False


def body(payload):
    return Response(json.dumps(payload).encode("utf-8"))


def text(value):
    return Response(value.encode("utf-8"))


class Discovery(unittest.TestCase):
    """The read token is the site's own, found the way a browser finds it."""

    def test_the_token_and_base_come_out_of_the_site_javascript(self):
        client = Client(delay=0)
        with mock.patch("urllib.request.urlopen", return_value=text(COMMON_JS)):
            self.assertEqual(client.token, "0123456789abcdef")
        self.assertEqual(client._base, "https://data.example.test")

    def test_the_base_falls_back_when_the_javascript_does_not_set_one(self):
        client = Client(delay=0)
        only_token = 'headers.common.Authorization = "Bearer abc123";'
        with mock.patch("urllib.request.urlopen", return_value=text(only_token)):
            self.assertEqual(client.token, "abc123")
        self.assertEqual(client._base, API)

    def test_a_missing_token_says_the_frontend_changed(self):
        client = Client(delay=0)
        with mock.patch("urllib.request.urlopen", return_value=text("// nothing")):
            with self.assertRaises(ApiError) as raised:
                client.token                                    # noqa: B018
        self.assertIn("frontend has changed", str(raised.exception))

    def test_an_unreachable_site_is_an_api_error_not_a_url_error(self):
        client = Client(delay=0)
        with mock.patch("urllib.request.urlopen",
                        side_effect=urllib.error.URLError("down")):
            with self.assertRaises(ApiError):
                client.token                                    # noqa: B018

    def test_the_token_is_discovered_once_and_then_reused(self):
        client = Client(delay=0)
        with mock.patch("urllib.request.urlopen", return_value=text(COMMON_JS)) as open_:
            client.token                                        # noqa: B018
            client.token                                        # noqa: B018
        self.assertEqual(open_.call_count, 1)


class Requests(unittest.TestCase):
    def setUp(self):
        self.client = Client(delay=0)
        self.client._token = "tok"
        # The retry path logs a warning by design; tests should not print it.
        logging.disable(logging.WARNING)
        self.addCleanup(logging.disable, logging.NOTSET)

    def responses(self, *values):
        """Patch urlopen to return each value in turn, recording the requests."""
        sent = []

        def fake(request, timeout=None):
            sent.append(request)
            value = values[min(len(sent) - 1, len(values) - 1)]
            if isinstance(value, Exception):
                raise value
            return value

        return mock.patch("urllib.request.urlopen", side_effect=fake), sent

    def test_the_request_carries_the_token_and_the_user_agent(self):
        patch, sent = self.responses(body({"entries": []}))
        with patch:
            self.client.get("games")
        self.assertEqual(sent[0].get_header("Authorization"), "Bearer tok")
        self.assertEqual(sent[0].get_header("User-agent"), USER_AGENT)
        self.assertIn(__version__, USER_AGENT)

    def test_the_query_is_posted_as_json(self):
        patch, sent = self.responses(body({"entries": []}))
        with patch:
            self.client.get("games", {"filter": {"seriesId": "s1"}})
        self.assertEqual(json.loads(sent[0].data.decode("utf-8")),
                         {"filter": {"seriesId": "s1"}})

    def test_an_error_field_in_the_body_is_raised(self):
        patch, _ = self.responses(body({"error": "no such collection"}))
        with patch, self.assertRaises(ApiError):
            self.client.get("nope")

    def test_a_client_error_is_not_retried(self):
        failure = urllib.error.HTTPError("u", 404, "gone", {}, None)
        patch, sent = self.responses(failure)
        with patch, self.assertRaises(ApiError):
            self.client.get("games")
        self.assertEqual(len(sent), 1)

    def test_a_server_error_is_retried_and_then_given_up_on(self):
        failure = urllib.error.HTTPError("u", 503, "busy", {}, None)
        patch, sent = self.responses(failure)
        with patch, mock.patch("time.sleep"), self.assertRaises(ApiError):
            self.client.get("games")
        self.assertEqual(len(sent), self.client.attempts)

    def test_a_server_error_that_clears_returns_the_body(self):
        failure = urllib.error.HTTPError("u", 500, "oops", {}, None)
        patch, sent = self.responses(failure, body({"entries": [1]}))
        with patch, mock.patch("time.sleep"):
            self.assertEqual(self.client.get("games"), {"entries": [1]})
        self.assertEqual(len(sent), 2)

    def test_a_torn_response_is_retried(self):
        patch, sent = self.responses(Response(b"{not json"), body({"entries": []}))
        with patch, mock.patch("time.sleep"):
            self.client.get("games")
        self.assertEqual(len(sent), 2)


class Caching(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client = Client(cache_dir=self.directory.name, delay=0)
        self.client._token = "tok"

    def test_a_second_identical_call_makes_no_request(self):
        with mock.patch("urllib.request.urlopen",
                        return_value=body({"entries": [1]})) as open_:
            first = self.client.get("games", {"a": 1})
        with mock.patch("urllib.request.urlopen") as second:
            again = self.client.get("games", {"a": 1})
        self.assertEqual(first, again)
        self.assertEqual(open_.call_count, 1)
        second.assert_not_called()

    def test_a_different_query_is_a_different_cache_entry(self):
        with mock.patch("urllib.request.urlopen", return_value=body({"entries": []})):
            self.client.get("games", {"a": 1})
        with mock.patch("urllib.request.urlopen",
                        return_value=body({"entries": []})) as open_:
            self.client.get("games", {"a": 2})
        open_.assert_called_once()

    def test_use_cache_false_refetches_and_still_writes(self):
        with mock.patch("urllib.request.urlopen", return_value=body({"entries": [1]})):
            self.client.get("games", {"a": 1})
        with mock.patch("urllib.request.urlopen",
                        return_value=body({"entries": [2]})) as open_:
            fresh = self.client.get("games", {"a": 1}, use_cache=False)
        open_.assert_called_once()
        self.assertEqual(fresh, {"entries": [2]})
        with mock.patch("urllib.request.urlopen") as third:
            self.assertEqual(self.client.get("games", {"a": 1}), {"entries": [2]})
        third.assert_not_called()

    def test_without_a_cache_directory_nothing_is_written(self):
        client = Client(cache_dir=None, delay=0)
        client._token = "tok"
        with mock.patch("urllib.request.urlopen", return_value=body({"entries": []})):
            client.get("games")
        self.assertIsNone(client.cache_dir)


class Throttle(unittest.TestCase):
    """The delay between requests is the politeness this project promises."""

    def run_two(self, readings):
        """Two requests over a scripted clock; returns the mocked ``time.sleep``."""
        client = Client(delay=0.5)
        client._token = "tok"
        remaining = list(readings)

        def clock():
            return remaining.pop(0) if len(remaining) > 1 else remaining[0]

        with mock.patch("time.monotonic", side_effect=clock), \
                mock.patch("time.sleep") as slept, \
                mock.patch("urllib.request.urlopen",
                           side_effect=lambda *a, **k: body({"e": []})):
            client.get("games", {"a": 1}, use_cache=False)
            client.get("games", {"a": 2}, use_cache=False)
        return slept

    def test_a_second_request_waits_out_the_remaining_delay(self):
        slept = self.run_two([100.0, 100.0, 100.1, 100.5])
        self.assertTrue(slept.called)
        self.assertAlmostEqual(slept.call_args[0][0], 0.4, places=6)

    def test_a_request_after_the_delay_does_not_sleep(self):
        self.run_two([100.0, 100.0, 200.0, 200.0]).assert_not_called()


class Convenience(unittest.TestCase):
    def setUp(self):
        self.client = Client(delay=0)
        self.client._token = "tok"

    def sent_query(self, call):
        captured = {}

        def fake(request, timeout=None):
            captured["query"] = json.loads(request.data.decode("utf-8"))
            captured["url"] = request.full_url
            return body({"entries": [{"_id": "x"}]})

        with mock.patch("urllib.request.urlopen", side_effect=fake):
            result = call()
        return captured, result

    def test_series_filters_by_year_only_when_one_is_given(self):
        captured, result = self.sent_query(lambda: self.client.series())
        self.assertEqual(captured["query"]["filter"], {})
        self.assertEqual(result, [{"_id": "x"}])
        captured, _ = self.sent_query(lambda: self.client.series(2099))
        self.assertEqual(captured["query"]["filter"], {"year": "2099"})

    def test_games_asks_only_for_published_fixtures_of_one_series(self):
        captured, _ = self.sent_query(lambda: self.client.games("s1"))
        self.assertEqual(captured["query"]["filter"],
                         {"seriesId": "s1", "published": True})
        self.assertTrue(captured["url"].endswith("/api/collections/get/games"))

    def test_teams_asks_for_one_series_in_table_order(self):
        captured, _ = self.sent_query(lambda: self.client.teams("s1"))
        self.assertEqual(captured["query"]["filter"], {"seriesId": "s1"})
        self.assertEqual(captured["query"]["sort"], {"order": 1})


if __name__ == "__main__":
    unittest.main()
