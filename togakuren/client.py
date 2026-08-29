"""Read-only client for the federation's public content API.

The federation's website is a Vue single-page application. Every page fetches its
content from a Cockpit CMS instance at ``data.f-togakuren.com`` using a read token
that the site ships to every browser inside ``common.js``. This client discovers
that token the same way a browser does rather than hardcoding it, so a rotated
token is picked up automatically and no credential lives in this repository.

Only public, already-rendered content is requested. Responses are cached on disk
so that a re-run costs no requests at all.
"""

import hashlib
import json
import logging
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

SITE = "https://www.f-togakuren.com"
API = "https://data.f-togakuren.com"
COMMON_JS = f"{SITE}/wp-content/themes/togakuren/js/common.js"

_TOKEN_RE = re.compile(r"""Authorization\s*=\s*["']Bearer\s+([0-9a-f]+)["']""")
_BASE_RE = re.compile(r"""axios\.defaults\.baseURL\s*=\s*["']([^"']+)["']""")

USER_AGENT = (
    "togakuren-analytics/0.1 (+https://github.com/sean-from-japan/togakuren-analytics) "
    "python-urllib"
)


class ApiError(RuntimeError):
    """Raised when the federation API cannot be reached or returns an error."""


class Client:
    """Polite, caching client for ``POST /api/collections/get/{name}``.

    Args:
        cache_dir: directory for raw JSON responses. ``None`` disables caching.
        delay: minimum seconds between network requests.
        timeout: per-request socket timeout in seconds.
    """

    def __init__(self, cache_dir=None, delay=0.5, timeout=30.0, attempts=3):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.timeout = timeout
        self.attempts = max(1, attempts)
        self._token = None
        self._base = API
        self._last_request = 0.0

    # -- token discovery ---------------------------------------------------

    def _discover(self):
        """Read the public read token out of the site's own JavaScript."""
        try:
            req = urllib.request.Request(COMMON_JS, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                source = res.read().decode("utf-8", "replace")
        except urllib.error.URLError as exc:
            raise ApiError(f"could not fetch {COMMON_JS}: {exc}") from exc

        token = _TOKEN_RE.search(source)
        if not token:
            raise ApiError(
                "no read token found in common.js; the site's frontend has changed"
            )
        base = _BASE_RE.search(source)
        self._token = token.group(1)
        self._base = base.group(1).rstrip("/") if base else API
        log.debug("discovered API base %s", self._base)

    @property
    def token(self):
        if self._token is None:
            self._discover()
        return self._token

    # -- requests ----------------------------------------------------------

    def _throttle(self):
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request = time.monotonic()

    def _post(self, collection, query):
        """One API call, retrying transient failures with a widening pause."""
        request = urllib.request.Request(
            f"{self._base}/api/collections/get/{collection}",
            data=json.dumps(query).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
                "User-Agent": USER_AGENT,
            },
        )
        last = None
        for attempt in range(self.attempts):
            self._throttle()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code < 500 or attempt == self.attempts - 1:
                    raise ApiError(f"{collection}: HTTP {exc.code}") from exc
                last = exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt == self.attempts - 1:
                    raise ApiError(f"{collection}: {exc}") from exc
                last = exc
            log.warning("%s: %s; retrying", collection, last)
            time.sleep(self.delay * 2 ** (attempt + 1))
        raise ApiError(f"{collection}: {last}")

    def _cache_path(self, collection, query):
        key = hashlib.sha256(
            json.dumps([collection, query], sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:20]
        return self.cache_dir / f"{collection}-{key}.json"

    def get(self, collection, query=None, use_cache=True):
        """Fetch one collection. Returns the decoded response body.

        Args:
            collection: e.g. ``"games"``, ``"series"``, ``"seriesTeams"``.
            query: Cockpit query body (``filter``, ``sort``, ``fields``, ``populate``).
            use_cache: read from and write to the on-disk cache.
        """
        query = query or {}
        path = self._cache_path(collection, query) if self.cache_dir else None

        if use_cache and path and path.exists():
            log.debug("cache hit %s", path.name)
            return json.loads(path.read_text(encoding="utf-8"))

        body = self._post(collection, query)

        if isinstance(body, dict) and "error" in body:
            raise ApiError(f"{collection}: {body['error']}")

        if path:
            path.write_text(
                json.dumps(body, ensure_ascii=False), encoding="utf-8"
            )
        return body

    # -- convenience -------------------------------------------------------

    def series(self, year=None):
        """All competition-seasons, newest first."""
        query = {"filter": {}, "sort": {"year": -1}, "limit": 500}
        if year:
            query["filter"]["year"] = str(year)
        return self.get("series", query).get("entries", [])

    def games(self, series_id):
        """Every published fixture of one series with team records embedded."""
        return self.get(
            "games",
            {
                "filter": {"seriesId": series_id, "published": True},
                "sort": {"section": 1, "date": 1},
                "populate": 1,
            },
        ).get("entries", [])

    def teams(self, series_id):
        """Squad rosters and the computed league table for one series."""
        return self.get(
            "seriesTeams",
            {"filter": {"seriesId": series_id}, "sort": {"order": 1}},
        ).get("entries", [])
