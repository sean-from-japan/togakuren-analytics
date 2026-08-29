"""Command line entry point: ``python -m togakuren <command>``."""

import argparse
import csv
import logging
import sys
from pathlib import Path

from . import __version__, dashboard, db, ingest, metrics, paths, privacy, report, trends
from .client import ApiError, Client


def _client(args):
    cache = None if args.no_cache else (args.cache or paths.cache())
    return Client(cache_dir=cache, delay=args.delay)


def _resolve_series(conn, value):
    """Accept a series id, or ``latest`` / a year plus a division name."""
    rows = metrics.series_list(conn)
    if not rows:
        raise SystemExit("no series loaded; run `ingest` first")
    if value in (None, "latest"):
        return rows[0]["id"]
    for row in rows:
        if row["id"] == value:
            return value
    # Every whitespace-separated term must appear, so "2026 1部" narrows a name
    # that "1部" alone matches seven times over.
    terms = value.lower().split()
    matches = [
        row for row in rows
        if all(term in f"{row['year']} {row['short_name']} {row['name']}".lower() for term in terms)
    ]
    if len(matches) == 1:
        return matches[0]["id"]
    if not matches:
        raise SystemExit(f"no loaded series matches {value!r}")
    listing = "\n".join(f"  {row['id']}  {row['year']}  {row['name']}" for row in matches)
    raise SystemExit(f"{value!r} matches several series:\n{listing}")


def cmd_series(args):
    """List the competitions the federation publishes."""
    for entry in _client(args).series(args.year):
        print(f"{entry['_id']}  {entry.get('year')}  {entry.get('name')}")


def cmd_ingest(args):
    target = Path(args.db or paths.database())
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(target)
    client = _client(args)
    if args.series:
        wanted = set(args.series)
        chosen = [entry for entry in client.series() if entry["_id"] in wanted]
        if not chosen:
            raise SystemExit("none of the given series ids exist")
        games = sum(ingest.ingest_series(conn, client, entry) for entry in chosen)
    else:
        games = ingest.ingest_all(conn, client, years=args.year)
    if args.drop_personal_data:
        db.drop_personal_data(conn)
        print("personal data removed from the database")
    print(f"\n{games} fixtures in {target}")
    for table, count in db.counts(conn).items():
        print(f"  {table:16}{count:>7}")


def cmd_list(args):
    conn = db.connect(args.db or paths.database())
    for row in metrics.series_list(conn):
        print(
            f"{row['id']}  {row['year']}  {(row['short_name'] or ''):12}"
            f"{row['completed'] or 0:>4}/{row['games']:<4} {row['name']}"
        )


def cmd_report(args):
    conn = db.connect(args.db or paths.database())
    series_id = _resolve_series(conn, args.series)
    salt = None
    if args.privacy == "pseudonym":
        salt = args.salt or privacy.new_salt()
    if args.public:
        rows = metrics.player_season(conn, series_id, min_minutes=args.min_minutes)
        privacy.check_public_safe(args.privacy, rows)
    html = report.build(
        conn, series_id, mode=args.privacy, salt=salt,
        min_minutes=args.min_minutes, top=args.top,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html):,} bytes, privacy={args.privacy})")


def cmd_dashboard(args):
    conn = db.connect(args.db or paths.database())
    series_id = _resolve_series(conn, args.series)
    salt = args.salt or (privacy.new_salt() if args.privacy == "pseudonym" else None)
    if args.public:
        rows = metrics.player_season(conn, series_id, min_minutes=0)
        privacy.check_public_safe(args.privacy, rows)
    html = dashboard.build(conn, series_id, mode=args.privacy, salt=salt)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html):,} bytes, privacy={args.privacy})")


def cmd_trends(args):
    """Everything that only shows up across several seasons."""
    conn = db.connect(args.db or paths.database())
    html = trends.build(conn, focus_team_id=args.club)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html):,} bytes, aggregates only)")


def cmd_export(args):
    conn = db.connect(args.db or paths.database())
    series_id = _resolve_series(conn, args.series)
    rows = metrics.player_season(conn, series_id, min_minutes=args.min_minutes)
    if args.privacy == "aggregate":
        raise SystemExit("aggregate mode has no per-player export; use `report`")
    if args.public:
        privacy.check_public_safe(args.privacy, rows)
    salt = args.salt or (privacy.new_salt() if args.privacy == "pseudonym" else None)
    names = dict(conn.execute("SELECT player_id, name FROM players"))

    columns = [
        "label", "team", "grade", "position", "apps", "starts", "sub_apps", "minutes",
        "shots", "goals", "yellows", "reds", "shots_per_90", "goals_per_90", "conversion",
    ]
    handle = open(args.out, "w", newline="", encoding="utf-8") if args.out else sys.stdout
    try:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            row = dict(row)
            row["label"] = privacy.label(
                row["player_id"], names.get(row["player_id"]), args.privacy, salt
            )
            writer.writerow(row)
    finally:
        if args.out:
            handle.close()
            print(f"wrote {args.out} ({len(rows)} rows, privacy={args.privacy})")


def cmd_privacy_check(args):
    """Report how identifiable a de-named export would still be."""
    conn = db.connect(args.db or paths.database())
    series_id = _resolve_series(conn, args.series)
    rows = metrics.player_season(conn, series_id, min_minutes=args.min_minutes)
    print(f"{len(rows)} players above {args.min_minutes} minutes\n")
    for identifiers in (
        ["team"], ["team", "position"], ["team", "position", "apps"],
        ["team", "position", "apps", "goals"],
    ):
        result = privacy.k_anonymity(rows, identifiers)
        share = 100 * result["unique"] / result["total"] if result["total"] else 0
        print(
            f"  {'+'.join(identifiers):34} k={result['k']:<3} "
            f"unique rows {result['unique']:>4}/{result['total']} ({share:.0f}%)"
        )
    print(
        "\nk=1 means at least one row can be matched back to a named person using the\n"
        "squad lists the federation already publishes, whatever the name column says."
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="togakuren",
        description="Collect and analyse Tokyo University Football Association fixtures.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--db", default=None,
        help=f"SQLite path (default: {paths.database()})",
    )
    parser.add_argument(
        "--cache", default=None,
        help=f"raw response cache directory (default: {paths.cache()})",
    )
    parser.add_argument("--no-cache", action="store_true", help="always hit the network")
    parser.add_argument("--delay", type=float, default=0.5, help="seconds between requests")

    subparsers = parser.add_subparsers(dest="command", required=True)

    remote = subparsers.add_parser("series", help="list competitions on the federation site")
    remote.add_argument("--year")
    remote.set_defaults(func=cmd_series)

    load = subparsers.add_parser("ingest", help="download fixtures into SQLite")
    load.add_argument("--year", nargs="*", help="restrict to these years")
    load.add_argument("--series", nargs="*", help="restrict to these series ids")
    load.add_argument(
        "--drop-personal-data", action="store_true",
        help="delete names and squad details after loading, keeping player ids",
    )
    load.set_defaults(func=cmd_ingest)

    listing = subparsers.add_parser("list", help="list series already in the database")
    listing.set_defaults(func=cmd_list)

    across = subparsers.add_parser(
        "trends", help="build the cross-season page (aggregates only, safe to publish)"
    )
    across.add_argument("--club", help="federation club id to open the trajectory on")
    across.add_argument("--out", default="reports/trends.html")
    across.set_defaults(func=cmd_trends)

    for name, handler, extra in (
        ("report", cmd_report, True),
        ("dashboard", cmd_dashboard, True),
        ("export", cmd_export, False),
        ("privacy-check", cmd_privacy_check, None),
    ):
        sub = subparsers.add_parser(
            name,
            help={
                "report": "build a standalone HTML report",
                "dashboard": "build an interactive HTML dashboard with a team selector",
                "export": "write per-player season rows as CSV",
                "privacy-check": "measure how identifiable a de-named export is",
            }[name],
        )
        sub.add_argument("--series", default="latest", help="series id, a search term, or 'latest'")
        sub.add_argument("--min-minutes", type=int, default=270)
        if extra is not None:
            sub.add_argument(
                "--privacy", choices=privacy.MODES,
                # Local viewing defaults to real names; anything meant to leave
                # the machine starts pseudonymous.
                default="pseudonym" if name == "export" else "full",
            )
            sub.add_argument("--salt", help="reuse a salt so pseudonyms stay stable")
            sub.add_argument(
                "--public", action="store_true",
                help="refuse to write anything unsafe to publish",
            )
        if extra:
            sub.add_argument("--out", default=f"reports/{name}.html")
            if name == "report":
                sub.add_argument("--top", type=int, default=20)
        elif extra is False:
            sub.add_argument("--out", help="CSV path (default: stdout)")
        sub.set_defaults(func=handler)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )
    try:
        args.func(args)
    except (ApiError, privacy.PrivacyError) as exc:
        raise SystemExit(f"error: {exc}") from exc
    return 0


if __name__ == "__main__":
    sys.exit(main())
