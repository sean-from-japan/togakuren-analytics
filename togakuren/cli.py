"""Command line entry point: ``python -m togakuren <command>``."""

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

from . import (__version__, analysis, compare, dashboard, db, ingest, intake,
               markdown, metrics, origins, paths, predict, privacy, rapm, report,
               sample, trends)
from .client import ApiError, Client


def _positive(value):
    """An argparse type for counts that cannot sensibly be zero.

    ``--runs 0`` divided by zero, and ``--runs -5`` was worse: the simulation
    loop simply did not run and every club came back with an expected zero
    points, which reads as an answer rather than as a mistake.
    """
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or more, not {number}")
    return number


def _database(args, path=None):
    """Open the database and have :func:`main` close it when the command ends.

    Every command used to open a connection and none of them closed it. That is
    harmless on a POSIX system and not on Windows, where an open SQLite handle
    keeps the file locked and a temporary directory cannot be removed around it.
    The command tests found it; the fix belongs here rather than in them.
    """
    conn = db.connect(path or args.db or paths.database())
    args.__dict__.setdefault("_open", []).append(conn)
    return conn


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
    conn = _database(args, target)
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
    conn = _database(args)
    for row in metrics.series_list(conn):
        print(
            f"{row['id']}  {row['year']}  {(row['short_name'] or ''):12}"
            f"{row['completed'] or 0:>4}/{row['games']:<4} {row['name']}"
        )


def cmd_report(args):
    conn = _database(args)
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
    conn = _database(args)
    series_id = _resolve_series(conn, args.series)
    salt = args.salt or (privacy.new_salt() if args.privacy == "pseudonym" else None)
    if args.public:
        rows = metrics.player_season(conn, series_id, min_minutes=0)
        privacy.check_public_safe(args.privacy, rows)
    html = dashboard.build(conn, series_id, mode=args.privacy, salt=salt, lang=args.lang)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html):,} bytes, privacy={args.privacy}, lang={args.lang})")


def cmd_trends(args):
    """Everything that only shows up across several seasons."""
    conn = _database(args)
    if args.format == "md":
        body = markdown.season_trends(conn, lang=args.lang)
    else:
        body = trends.build(conn, focus_team_id=args.club, lang=args.lang)
    # Every language gets an explicit suffix. This prevents one language from
    # looking like the default and keeps a second language from overwriting it.
    out = Path(args.out or (f"docs/{markdown.localized_filename('SEASON_TRENDS', args.lang)}"
                            if args.format == "md"
                            else "reports/trends.html"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(f"wrote {out} ({len(body):,} bytes, aggregates only)")


def _write_profile(conn, series, out_dir, lang, figure):
    slug = markdown.season_slug(series["year"], series["division"])
    out = Path(out_dir) / markdown.localized_filename(slug, lang)
    policy = "../" + markdown.localized_filename("DATA_POLICY", lang)
    out.write_text(
        markdown.team_profiles(conn, series["id"], lang=lang, figure=figure, policy=policy),
        encoding="utf-8",
    )
    return out


def cmd_profiles(args):
    """One division as Markdown, or every completed league season at once."""
    conn = _database(args)
    if not args.all:
        series_id = _resolve_series(conn, args.series)
        text = markdown.team_profiles(
            conn, series_id, lang=args.lang,
            figure=args.figure or f"figures/{args.lang}/fig-fingerprints.png")
        out = Path(args.out or f"docs/{markdown.localized_filename('TEAM_PROFILES', args.lang)}")
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
                _write_profile(conn, series, out_dir, lang,
                               f"../figures/{lang}/fig-fingerprints.png")
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
            f"[{lang}]({markdown.localized_filename(slug, lang)})" for lang in langs
        )
        state = "" if series["completed"] >= series["games"] else " *(in progress / 進行中)*"
        rows.append(
            f"| {series['year']} | {series['division']}{state} | "
            f"{series['completed']}/{series['games']} | {links} |"
        )
    return (
        "# Season profiles / シーズン別チーム分析\n\n"
        "One document per league season, generated by `togakuren profiles --all`. "
        "Each language is named explicitly in the filename.\n\n"
        "各シーズン・各部の文書を `togakuren profiles --all` で生成しています。"
        "ファイル名には言語を明記しています。\n\n"
        "Aggregates only / 集計値のみ — [English data policy](../DATA_POLICY.en.md) · "
        "[日本語のデータ方針](../DATA_POLICY.ja.md)\n\n"
        "| Season / 年度 | Division / 部 | Fixtures / 試合 | Document / 文書 |\n"
        "| --- | --- | --: | --- |\n"
        + "\n".join(rows) + "\n"
    )



def cmd_forecast(args):
    """Probabilities for the fixtures that have not been played yet."""
    conn = _database(args)
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
    conn = _database(args)
    rows = rapm.segments(conn, min_year=args.min_year, league_only=not args.include_cups)
    if not rows:
        raise SystemExit("no usable segments; run `ingest` first")
    loose = rapm.segments(conn, min_year=args.min_year,
                          league_only=not args.include_cups, reconcile=False)
    games, all_games = len({r.game for r in rows}), len({r.game for r in loose})
    print(f"{len(rows):,} segments over {games:,} fixtures "
          f"({all_games - games:,} left out: timed goals do not add up to the score)")

    if args.validate or args.forward:
        if args.forward:
            dates = {match["game_id"]: match["date"] for match in predict.load(conn)}
            try:
                scores, penalties = rapm.forward(rows, dates,
                                                 min_minutes=args.min_minutes,
                                                 nested=args.tune)
            except ValueError as exc:
                # Too few fixtures for a 60/40 cut inside a season. Say that
                # rather than showing the caller a traceback.
                raise SystemExit(f"cannot split this sample forwards: {exc}") from exc
            train, test = rapm.season_split(rows, dates)
            header = (f"Forward split, first 60% of each season "
                      f"({len({r.game for r in train}):,} fixtures) predicting the rest "
                      f"({len({r.game for r in test}):,})")
        else:
            scores, penalties = rapm.validate(rows, min_minutes=args.min_minutes,
                                              nested=args.tune)
            header = "Grouped 5-fold CV, match goal-difference error"
        baseline = scores["zero"]
        picked = ("penalties chosen inside the training data only"
                  if args.tune else "penalties from the module constants, which "
                                    "were chosen over these same fixtures")
        print(f"\n{header}\n({picked})\n")
        print(f"{'model':16} {'MSE':>8} {'vs zero':>9}")
        for name in ("zero", "clubs", "players", "clubs+players"):
            share = "" if name == "zero" else f"{(scores[name] - baseline) / baseline:9.2%}"
            print(f"{name:16} {scores[name]:8.4f} {share:>9}")
        gain = (scores["clubs"] - scores["clubs+players"]) / scores["clubs"]
        print(f"\nknowing the players and not just the clubs: {gain:+.2%}")
        if args.tune:
            print("\nchosen (player, club)")
            for name in ("clubs", "players", "clubs+players"):
                shown = ", ".join(f"({p:g}, {c:g})" for p, c in penalties[name])
                print(f"  {name:16} {shown}")
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
    print("Player-level output, so it stays on this machine; see docs/DATA_POLICY.en.md.")


def cmd_backtest(args):
    """Score the models against the class prior, walking forward through time."""
    conn = _database(args)
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


def cmd_compare(args):
    """Measure each division as a league in its own right.

    Divisions are kept apart rather than pooled: a pyramid measured as one thing
    reports the gap between its tiers, not the balance inside any of its leagues.
    """
    conn = _database(args)
    matches = [match for match in predict.load(conn)
               if match["played"] and match["type"] == "league"
               and match["goals"][0] is not None]
    grouped = {}
    for match in matches:
        grouped.setdefault(match["division"], []).append(match)

    rows, skipped = [], []
    for division, played in sorted(grouped.items()):
        if len(played) < args.min_fixtures:
            skipped.append((division, f"{len(played)} fixtures"))
            continue
        try:
            row = compare.measure(played)
        except ValueError as exc:
            skipped.append((division, str(exc)))
            continue
        row["division"] = division
        rows.append(row)
    if not rows:
        raise SystemExit("no division has enough seasons to measure; run `ingest` first")

    print(f"{'division':14} {'clubs':>6} {'fx/club':>8} {'talent sd':>10} "
          f"{'N-S':>5} {'draws':>7} {'goals':>6} {'gain':>8} {'half-life':>10}")
    for row in rows:
        print(f"{row['division'][:14]:14} {row['clubs']:6.0f} "
              f"{row['fixtures_per_club']:8.0f} {row['talent_spread']:10.3f} "
              f"{row['noll_scully']:5.2f} {row['draw_rate']:7.1%} "
              f"{row['goals_per_fixture']:6.2f} {row['gain']:+8.4f} "
              f"{row['half_life']:9}d")
    for division, why in skipped:
        print(f"{division[:14]:14} not measured: {why}")

    if not args.reference:
        return
    reference = json.loads(Path(args.reference).read_text(encoding="utf-8"))
    fitted = compare.line(reference)
    print(f"\nAgainst {fitted['n']} reference leagues: "
          f"gain = {fitted['intercept']:+.4f} + {fitted['slope']:.3f} x spread, "
          f"residual sd {fitted['residual_sd']:.4f}\n")
    print(f"{'division':14} {'expected':>9} {'actual':>8} {'residual':>9} {'in range':>9}")
    for row in rows:
        placed = compare.place(row, fitted)
        print(f"{row['division'][:14]:14} {placed['expected_gain']:+9.4f} "
              f"{row['gain']:+8.4f} {placed['residual_sd']:+8.2f}sd "
              f"{'yes' if placed['inside_reference_spread'] else 'NO':>9}")


def cmd_intake(args):
    """What the squad list says before the season starts."""
    conn = _database(args)
    rows = intake.squad_rows(conn)
    if not rows:
        raise SystemExit("no season has both a squad list and a table; run `ingest` first")
    if args.completed_only:
        latest = max(row["year"] for row in rows)
        rows = [row for row in rows if row["year"] != latest]

    if args.validate:
        scored = intake.evaluate(rows)
        print(f"Leave-one-season-out, predictions pooled. Baseline is the division average.\n")
        for title, key, n in (
            ("clubs with a previous season", "with_previous", scored["n_with_previous"]),
            ("every club, previous season or not", "every_club", scored["n_all"]),
        ):
            print(f"{title} (n={n})")
            for model in scored[key]:
                print(f"  {model['label']:<42} RMSE {model['rmse']:.4f}  "
                      f"{model['gain']:+6.1%}  r={model['r']:+.3f}")
            print()
        print("Correlation with the season's result, split by what the club just did")
        print(f"  {'':<12}{'clubs':>7}{'last table':>13}{'squad list':>13}")
        for row in intake.by_move(rows):
            print(f"  {row['move']:<12}{row['n']:>7}{row['last_table']:>+13.3f}"
                  f"{row['squad_list']:>+13.3f}")
        print()
        print("Championship and academy share by division, which the measure was never told")
        for row in intake.division_pedigree(rows):
            print(f"  {row['year']} level {row['level']}  {row['clubs']:>2} clubs  "
                  f"championship {row['champions']:6.1%}  academy {row['youth']:5.1%}")
        return

    year = args.year or max(row["year"] for row in rows)
    table = intake.preseason_table(rows, year, level=args.level)
    if not table:
        raise SystemExit(f"nothing to rank for {year} at level {args.level}")
    print(f"{year}, level {args.level}: ranked as the squad lists had it before kick-off")
    print(f"  {'club':<22}{'predicted':>10}{'actual':>9}{'champion school':>17}{'academy':>9}")
    for row in table:
        print(f"  {row['name'][:20]:<22}{row['predicted']:+10.2f}{row['result']:+9.2f}"
              f"{row['champions']:16.0%}{row['youth']:9.0%}")
    print(f"\n  correlation over the {len(table)} clubs: "
          f"{intake.correlation([r['predicted'] for r in table], [r['result'] for r in table]):+.3f}")
    print("  Both columns are standardised inside the division, so 0 is average and the\n"
          "  units are its own standard deviations.")


def cmd_sample(args):
    """Player-level output over a synthetic season, safe to publish."""
    conn = _database(args, ":memory:")
    series_id = sample.generate(conn, seed=args.seed)
    text = markdown.player_document(
        conn, series_id, lang=args.lang, min_minutes=args.min_minutes, top=args.top
    )
    out = Path(args.out or f"docs/{markdown.localized_filename('PLAYER_ANALYSIS_SAMPLE', args.lang)}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out} ({len(text):,} bytes, lang={args.lang}, invented data)")


def cmd_export(args):
    conn = _database(args)
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
    conn = _database(args)
    series_id = _resolve_series(conn, args.series)
    rows = metrics.player_season(conn, series_id, min_minutes=args.min_minutes)
    # The squad list carries one more ordinary-looking analytical column, and
    # what it does to the table below is the reason no per-player output here
    # ever includes it. See docs/DATA_POLICY.en.md.
    schools = {
        row[0]: origins.split_origin(row[1])[1] or "-"
        for row in conn.execute(
            "SELECT player_id, former_team FROM squad_members WHERE series_id = ?",
            (series_id,),
        )
    }
    for row in rows:
        row["school"] = schools.get(row["player_id"], "-")
    print(f"{len(rows)} players above {args.min_minutes} minutes\n")
    for identifiers in (
        ["team"], ["team", "position"], ["team", "position", "apps"],
        ["team", "position", "apps", "goals"],
        ["school"], ["team", "school"], ["team", "position", "apps", "school"],
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
    profiles.add_argument("--figure", help="path to the fingerprint figure, "
                          "relative to the document (default: the one for --lang)")
    profiles.add_argument("--out")
    profiles.set_defaults(func=cmd_profiles)

    against = subparsers.add_parser(
        "compare",
        help="measure each division as a league: balance, match shape, predictability",
    )
    against.add_argument("--min-fixtures", type=_positive, default=140,
                         help="skip a division with fewer played fixtures than this")
    against.add_argument(
        "--reference",
        help="JSON list of {talent_spread, gain} for leagues to place these against; "
             "see docs/LEAGUE_COMPARISON.en.md for how one is built",
    )
    against.set_defaults(func=cmd_compare)

    demo = subparsers.add_parser(
        "sample",
        help="write the player-level document over an invented season (no real person)",
    )
    demo.add_argument("--lang", choices=sorted(markdown.LABELS), default="en")
    demo.add_argument("--seed", type=int, default=20260829)
    demo.add_argument("--min-minutes", type=int, default=270)
    demo.add_argument("--top", type=int, default=25)
    demo.add_argument("--out")
    demo.set_defaults(func=cmd_sample)

    across = subparsers.add_parser(
        "trends", help="build the cross-season page (aggregates only, safe to publish)"
    )
    across.add_argument("--club", help="federation club id to open the trajectory on")
    across.add_argument("--format", choices=["html", "md"], default="html")
    across.add_argument("--lang", choices=sorted(markdown.LABELS), default="en")
    across.add_argument("--out")
    across.set_defaults(func=cmd_trends)

    preseason = subparsers.add_parser(
        "intake", help="what the squad list predicts before a ball is kicked"
    )
    preseason.add_argument("--year", help="season to rank (default: the most recent)")
    preseason.add_argument("--level", type=int, default=1,
                           help="league level, 1 being the top division")
    preseason.add_argument("--validate", action="store_true",
                           help="score every model out of sample instead of ranking a division")
    preseason.add_argument("--completed-only", action="store_true",
                           help="drop the most recent season, which is still being played")
    preseason.set_defaults(func=cmd_intake)

    forecast = subparsers.add_parser(
        "forecast", help="win/draw/loss probabilities for the fixtures still to play"
    )
    forecast.add_argument("--series", default="latest", help="series id, a search term, or 'latest'")
    forecast.add_argument("--runs", type=_positive, default=10000,
                          help="simulated seasons")
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
    ratings.add_argument("--forward", action="store_true",
                         help="score the first 60% of each season against the rest of "
                              "it, instead of cross-validating. The harder test")
    ratings.add_argument("--tune", action="store_true",
                         help="with --validate, choose the ridge penalties inside each "
                              "training fold rather than using the constants, which were "
                              "chosen over every fixture being scored. Slower and honest")
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
        if name == "dashboard":
            sub.add_argument("--lang", choices=sorted(dashboard.TEXT), default="en")
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
    finally:
        for conn in args.__dict__.get("_open", ()):
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
