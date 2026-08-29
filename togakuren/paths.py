"""Where the collected data lives.

Deliberately outside the working directory. The database holds names and squad
details of real people, so the default location is a per-user data directory
that no repository, backup script or ``git add .`` is going to sweep up by
accident. Override with ``$TOGAKUREN_HOME`` or the ``--db``/``--cache`` flags.

On macOS there is a second reason: a database under ``~/Documents`` has been
observed to fail mid-ingest with ``sqlite3.OperationalError: disk I/O error``
once the process has also made network requests, which looks like the privacy
protections around that directory. Application Support has no such problem.
"""

import os
import sys
from pathlib import Path

APP = "togakuren-analytics"


def home():
    """Root directory for this tool's data."""
    override = os.environ.get("TOGAKUREN_HOME")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / APP
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / APP


def database():
    return home() / "togakuren.sqlite3"


def cache():
    return home() / "cache"
