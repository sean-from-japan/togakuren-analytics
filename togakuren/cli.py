"""Command line entry point: ``python -m togakuren <command>``."""

import argparse
import csv
import logging
import sys
from pathlib import Path

from . import (__version__, analysis, dashboard, db, ingest, markdown, metrics, paths,
               predict, privacy, rapm, report, sample, trends)
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
    if args.format == "md":
        body = markdown.season_trends(conn, lang=args.lang)
    else:
        body = trends.build(conn, focus_team_id=args.club)
    out = Path(args.out or (f"docs/SEASON_TRENDS.md" if args.format == "md"
                            else "reports/trends.html"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(f"wrote {out} ({len(body):,} bytes, aggregates only)")


def _write_profile(conn, series, out_dir, lang, figure):
    slug = markdown.season_slug(series["year"], series["division"])
    suffix = "" if lang == "en" else f".{lang}"
    out = Path(out_dir) / f"{slug}{suffix}.md"
    policy = "../DATA_POLICY.md" if lang == "en" else "../DATA_POLICY.ja.md"
    out.write_text(
        markdown.team_profiles(conn, series["id"], lang=lang, figure=figure, policy=policy),
        encoding="utf-8",
    )
    return out


def cmd_profiles(args):
    """One division as Markdown, or every completed league season at once."""
    conn = db.connect(args.db or paths.database())
    if not args.all:
        series_id = _resolve_series(conn, args.series)
        text = markdown.team_profiles(conn, series_id, lang=args.lang, figure=args.figure)
        out = Path(args.out or "docs/TEAM_PROFILES.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out} ({len(text):,} bytes, lang={args.lang}, aggregates only)")
        return

    out_dir = Path(args.out or "docs/seasons")
    out_dir.mkdir(parents=True, exist_ok=True)
    # A season that is over will never change, so its document is worth keeping
    # in the repository rather than regenerating to read.
    written = []
    for series in analysis.league_series(conn):
        if not series["completed"]:
            continue
        for lang in args.lang_all:
            written.append(
                _write_profile(conn, series, out_dir, lang, "../figures/fig-fingerprints.png")
            )
    index = out_dir / "README.md"
    index.write_text(_seasons_index(conn, args.lang_all), encoding="utf-8")
    print(f"wrote {len(written)} documents and {index}")


def _seasons_index(conn, langs):
    rows = []
    for series in analysis.league_series(conn):
        if not series["completed"]:
            continue
        slug = markdown.season_slug(series["year"], series["division"])
        links = " · ".join(
            f"[{lang}]({slug}{'' if lang == 'en' else '.' + lang}.md)" for lang in langs
        )
        state = "" if series["completed"] >= series["games"] else " *(in progress)*"
        rows.append(
            f"| {series['year']} | {series['division']}{state} | "
            f"{series['completed']}/{series['games']} | {links} |"
        )
    return (
        "# Season profiles\n\n"
        "One document per league season, generated by `togakuren profiles --all`.\n"
        "Seasons before 2026 are finished, so their documents are fixed.\n\n"
        "Aggregates only — no individual appears in any of them; see "
        "[../DATA_POLICY.md](../DATA_POLICY.md).\n\n"
        "| Season | Division | Fixtures | Document |\n| --- | --- | --: | --- |\n"
        + "\n".join(rows) + "\n"
    )



def cmd_forecast(args):
    """Probabilities for the fixtures that have not been played yet."""
    conn = db.connect(args.db or paths.database())
    series_id = _resolve_series(conn, args.series)
    matches = predict.load(conn)
    remaining = predict.upcoming(matches, series_id)
    if not remaining:
        raise SystemExit("every fixture in that series has been played")

    cutoff = predict.as_of(matches)
    model = predict.Poisson()
    predict.fit_through(model, matches, cutoff)

    print(f"{remaining[0]['series_name']} {remaining[0]['year']}: "
          f"{len(remaining)} fixtures to play, as of {cutoff}\n")
    print(f"{'date':11} {'fixture':44} {'win':>6} {'draw':>6} {'win':>6}  expected")
    for match in remaining:
        first, second = match["names"]
        chances = model.predict(match)
        goals = model.rates(match)
        when = "  TBC     " if predict.undated(match, cutoff) else str(match["date"])
        print(f"{when} {first[:20]:20} v {second[:20]:20} "
              f"{chances[0]:6.1%} {chances[1]:6.1%} {chances[2]:6.1%}  "
              f"{goals[0]:.1f}-{goals[1]:.1f}")

    played = [m for m in matches if m["series_id"] == series_id and m["played"]]
    points, positions = predict.simulate(model, played, remaining, runs=args.runs)
    names = {m["clubs"][i]: m["names"][i] for m in matches if m["series_id"] == series_id
             for i in (0, 1)}
    standing = predict.table(played)
    print(f"\nProjected table after {args.runs:,} simulated seasons\n")
    print(f"{'club':24} {'pl':>3} {'pts':>4} {'proj':>6} {'1st':>7} {'top3':>7} {'last':>7}")
    for club in sorted(points, key=lambda c: -points[c]):
        place = positions[club]
        total = sum(place.values()) or 1
        last = max(place) if place else 0
        print(f"{(names.get(club) or club)[:24]:24} {standing[club][0]:3} {standing[club][1]:4} "
              f"{points[club]:6.1f} {place[1]/total:7.1%} "
              f"{sum(place[p] for p in (1, 2, 3))/total:7.1%} {place[last]/total:7.1%}")
    print("\nOne club's odds, not advice, and no player-level claim is made.")


def cmd_ratings(args):
    """Adjusted plus-minus: how a player moves goal difference while on the pitch.

    The validation table is aggregate and safe to quote. The leaderboard is
    player-level, so it prints here and is never written to a file.
    """
    conn = db.connect(args.db or paths.database())
    rows = rapm.segments(conn, min_year=args.min_year, league_only=not args.include_cups)
    if not rows:
        raise SystemExit("no usable segments; run `ingest` first")
    loose = rapm.segments(conn, min_year=args.min_year,
                          league_only=not args.include_cups, reconcile=False)
    games, all_games = len({r.game for r in rows}), len({r.game for r in loose})
    print(f"{len(rows):,} segments over {games:,} fixtures "
          f"({all_games - games:,} left out: timed goals do not add up to the score)")

    if args.validate:
        scores = rapm.validate(rows, min_minutes=args.min_minutes)
        baseline = scores["zero"]
        print(f"\nGrouped {5}-fold CV, match goal-difference error\n")
        print(f"{'model':16} {'MSE':>8} {'vs zero':>9}")
        for name in ("zero", "clubs", "players", "clubs+players"):
            share = "" if name == "zero" else f"{(scores[name] - baseline) / baseline:9.2%}"
            print(f"{name:16} {scores[name]:8.4f} {share:>9}")
        gain = (scores["clubs"] - scores["clubs+players"]) / scores["clubs"]
        print(f"\nknowing the players and not just the clubs: {gain:+.2%}")
        return

    ratings, home, _, _ = rapm.fit(rows, min_minutes=args.min_minutes)
    played = rapm.minutes(rows)
    names = {row[0]: row[1] for row in conn.execute("SELECT player_id, name FROM players")}
    print(f"home advantage {home:+.3f} goals per 90; {len(ratings):,} players rated "
          f"at {args.min_minutes}+ minutes\n")
    order = sorted(ratings, key=ratings.get, reverse=True)
    for label, group in (("highest", order[:args.top]), ("lowest", order[-args.top:])):
        print(f"{label}\n{'player':24} {'minutes':>8} {'per 90':>8}")
        for player in group:
            print(f"{(names.get(player) or player)[:24]:24} "
                  f"{played[player]:8,} {ratings[player]:+8.3f}")
        print()
    print("Player-level output, so it stays on this machine; see docs/DATA_POLICY.md.")


def cmd_backtest(args):
    """Score the models against the class prior, walking forward through time."""
    conn = db.connect(args.db or paths.database())
    matches = predict.load(conn)
    models = [
        predict.Prior(),
        predict.Elo(k=60, regress=0.5, name="elo"),
        predict.Poisson(home=False, name="poisson (no home term)"),
        predict.Poisson(name="poisson"),
    ]
    def keep(match):
        if args.league_only and match["type"] != "league":
            return False
        return args.until is None or match["year"] <= args.until
    predictions, actuals, scored = predict.walk_forward(
        models, matches, start=args.start, keep=keep
    )
    if not actuals:
        raise SystemExit("nothing to score; run `ingest` first")

    print(f"{len(actuals):,} fixtures from {scored[0]['date']} to {scored[-1]['date']}"
          f"{' (league only)' if args.league_only else ''}\n")
    print(f"{'model':26} {'log loss':>9} {'Brier':>7} {'accuracy':>9}")
    for model in models:
        rows = predictions[model.name]
        print(f"{model.name:26} {predict.log_loss(rows, actuals):9.4f} "
              f"{predict.brier(rows, actuals):7.4f} {predict.accuracy(rows, actuals):9.1%}")

    best = min(models[1:], key=lambda m: predict.log_loss(predictions[m.name], actuals))
    print(f"\nCalibration of {best.name}: predicted against observed\n")
    print(f"{'band':>12} {'n':>7} {'predicted':>10} {'observed':>9}")
    for low, high, count, predicted, observed in predict.calibration(
        predictions[best.name], actuals
    ):
        print(f"{low:5.0%}-{high:<6.0%} {count:7,} {predicted:10.1%} {observed:9.1%}")


def cmd_sample(args):
    """Player-level output over a synthetic season, safe to publish."""
    conn = db.connect(":memory:")
    series_id = sample.generate(conn, seed=args.seed)
    text = markdown.player_document(
        conn, series_id, lang=args.lang, min_minutes=args.min_minutes, top=args.top
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({len(text):,} bytes, lang={args.lang}, invented data)")


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

    profiles = subparsers.add_parser(
        "profiles", help="write the division as Markdown (aggregates only)"
    )
    profiles.add_argument("--series", default="latest")
    profiles.add_argument("--lang", choices=sorted(markdown.LABELS), default="en")
    profiles.add_argument(
        "--all", action="store_true",
        help="write one document per completed league season into --out (a directory)",
    )
    profiles.add_argument(
        "--lang-all", nargs="+", choices=sorted(markdown.LABELS), default=["en", "ja"],
        help="languages to emit with --all",
    )
    profiles.add_argument("--figure", default="figures/fig-fingerprints.png")
    profiles.add_argument("--out")
    profiles.set_defaults(func=cmd_profiles)

    demo = subparsers.add_parser(
        "sample",
        help="write the player-level document over an invented season (no real person)",
    )
    demo.add_argument("--lang", choices=sorted(markdown.LABELS), default="en")
    demo.add_argument("--seed", type=int, default=20260829)
    demo.add_argument("--min-minutes", type=int, default=270)
    demo.add_argument("--top", type=int, default=25)
    demo.add_argument("--out", default="docs/PLAYER_ANALYSIS_SAMPLE.md")
    demo.set_defaults(func=cmd_sample)

    across = subparsers.add_parser(
        "trends", help="build the cross-season page (aggregates only, safe to publish)"
    )
    across.add_argument("--club", help="federation club id to open the trajectory on")
    across.add_argument("--format", choices=["html", "md"], default="html")
    across.add_argument("--lang", choices=sorted(markdown.LABELS), default="en")
    across.add_argument("--out")
    across.set_defaults(func=cmd_trends)

    forecast = subparsers.add_parser(
        "forecast", help="win/draw/loss probabilities for the fixtures still to play"
    )
    forecast.add_argument("--series", default="latest", help="series id, a search term, or 'latest'")
    forecast.add_argument("--runs", type=int, default=10000, help="simulated seasons")
    forecast.set_defaults(func=cmd_forecast)

    backtest = subparsers.add_parser(
        "backtest", help="score the forecast models against the class prior"
    )
    backtest.add_argument("--start", default="2022", help="first season to score")
    backtest.add_argument("--until", help="last season to score, for reproducing a tuning window")
    backtest.add_argument("--league-only", action="store_true",
                          help="skip cup ties, which are single fixtures between divisions")
    backtest.set_defaults(func=cmd_backtest)

    ratings = subparsers.add_parser(
        "ratings", help="adjusted plus-minus ratings, and how much they add over the club"
    )
    ratings.add_argument("--min-year", default="2022",
                         help="first season to use; player records begin in 2022")
    ratings.add_argument("--min-minutes", type=int, default=rapm.MIN_MINUTES,
                         help="minutes a player needs before they get a column of their own")
    ratings.add_argument("--include-cups", action="store_true",
                         help="add cup ties, which are single fixtures between divisions")
    ratings.add_argument("--validate", action="store_true",
                         help="print the cross-validation table instead of the players")
    ratings.add_argument("--top", type=int, default=15, help="players to show at each end")
    ratings.set_defaults(func=cmd_ratings)

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
