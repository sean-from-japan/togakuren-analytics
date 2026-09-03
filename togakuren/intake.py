"""Preseason strength from the squad list, scored against last year's table.

Everything else in this project measures a season that is already happening. This
measures the moment before one starts, from the only thing that exists then: the
registration list. It names every player, their academic year, and the high
school or club youth side they arrived from, and it is published before a ball is
kicked.

The list is turned into two signals. **Pedigree** is how often a player's high
school won its prefecture and reached the All-Japan Championship — an external
rating that knows nothing about this league (``reference-schools.json``).
**Youth** is the share of the squad that came through a professional club's
academy instead of school football.

The baseline is the only one that matters: what the previous season's table
already told you. Beating a coin flip is not a result; beating the table is.

Two leaks were closed before the numbers meant anything, and both cost a chunk
of the effect when they were:

* Rating schools on seasons that include the season being predicted. Scoring is
  leave-one-season-out, so a season is always predicted by a model that never
  saw it.
* Rating schools on their own graduates' results. An earlier version rated each
  school by how much its graduates played, which is endogenous — an affiliated
  school feeds one university every year, so the rating quietly carried that
  university's identity. Out of sample it was worth +1.0%. It was replaced by
  the external championship list, which cannot know anything about this league.

Everything here is a club-level aggregate. No per-player row carries a school:
adding that one column makes 97% of a division uniquely identifiable, which is
measured in ``docs/DATA_POLICY.en.md``.
"""

import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from . import analysis, origins

#: The external rating, shipped with the package because nothing works without
#: it. Editions 97-104 of the All-Japan High School Championship, from Japanese
#: Wikipedia under CC BY-SA 4.0 — the file names its own source.
REFERENCE = Path(__file__).resolve().parent / "reference-schools.json"


def championship_editions(path=None):
    """``canonical school key -> number of editions it qualified for``."""
    data = json.loads(Path(path or REFERENCE).read_text(encoding="utf-8"))
    counts = defaultdict(set)
    for edition, schools in data["editions"].items():
        for name in schools:
            counts[origins.match_key(name)].add(edition)
    return {key: len(editions) for key, editions in counts.items()}


def _standardise(values):
    """Z-scores against the group's own mean. A flat group is all zeros."""
    if len(values) < 2:
        return [0.0] * len(values)
    mean = statistics.mean(values)
    spread = statistics.pstdev(values)
    return [(v - mean) / spread if spread else 0.0 for v in values]


def squad_rows(conn, reference=None):
    """One row per club-season: the squad list turned into numbers.

    Only seasons with squad lists and a finished-enough table appear, and every
    value is standardised inside its own division and year. That is deliberate:
    an unstandardised pedigree score would mostly be measuring which division a
    club is in, which is not a prediction of anything.
    """
    editions = championship_editions(reference)
    series = {s["id"]: s for s in analysis.league_series(conn)}
    ladder = analysis.season_ladder(conn)
    club_of = {row["id"]: row["team_id"] for row in conn.execute("SELECT id, team_id FROM teams")}
    names = {row["team_id"]: row["short_name"] or row["name"] for row in conn.execute(
        "SELECT team_id, short_name, name FROM teams")}

    squads = defaultdict(list)
    for row in conn.execute(
        "SELECT series_id, team_pk, former_team, grade FROM squad_members"
    ):
        season = series.get(row["series_id"])
        if not season or not season["has_player_data"]:
            continue
        club, school = origins.split_origin(row["former_team"])
        squads[(season["year"], club_of[row["team_pk"]])].append({
            "grade": row["grade"],
            "youth": bool(club),
            "editions": editions.get(origins.match_key(school), 0) if school else 0,
        })

    outcome, level, divisions = {}, {}, defaultdict(list)
    for row in conn.execute(
        """SELECT t.team_id, t.series_id, st.points, st.played
             FROM teams t JOIN standings st ON st.team_pk = t.id
            WHERE st.played > 0"""
    ):
        season = series.get(row["series_id"])
        if not season:
            continue
        key = (season["year"], row["team_id"])
        outcome[key] = row["points"] / row["played"]
        level[key] = ladder.get(season["year"], {}).get(season["division"])
        divisions[(season["year"], season["division"])].append(key)

    # A club's result is only comparable inside its own division and season, so
    # everything is expressed as a z-score there. A division too small to have a
    # spread is dropped rather than given a made-up one.
    result_z = {}
    for keys in divisions.values():
        if len(keys) < 4:
            continue
        for key, value in zip(keys, _standardise([outcome[k] for k in keys])):
            result_z[key] = value

    rows = []
    for (year, club), squad in squads.items():
        if (year, club) not in result_z or not squad:
            continue
        first_years = [p for p in squad if p["grade"] == "1"]
        rows.append({
            "year": year, "club": club, "name": names.get(club, club),
            "level": level.get((year, club)), "size": len(squad),
            "result": result_z[(year, club)],
            "pedigree": statistics.mean(p["editions"] for p in squad),
            "champions": sum(1 for p in squad if p["editions"]) / len(squad),
            "youth": sum(1 for p in squad if p["youth"]) / len(squad),
            "first_year_share": len(first_years) / len(squad),
        })

    years = sorted({row["year"] for row in rows})
    for row in rows:
        index = years.index(row["year"])
        previous = (years[index - 1], row["club"]) if index else None
        if previous and previous in result_z:
            row["previous"] = result_z[previous]
            # Positive when the club went up a level: levels count downward.
            row["step"] = (level.get(previous) or 0) - (row["level"] or 0)

    by_division = defaultdict(list)
    for row in rows:
        by_division[(row["year"], row["level"])].append(row)
    for group in by_division.values():
        for field in ("pedigree", "champions", "youth"):
            for row, value in zip(group, _standardise([r[field] for r in group])):
                row[field + "_z"] = value
    return rows


def fit(rows, features):
    """Ordinary least squares by hand. The systems here are 2x2 to 5x5."""
    design = [[1.0] + [row[f] for f in features] for row in rows]
    target = [row["result"] for row in rows]
    width = len(features) + 1
    left = [[sum(x[a] * x[b] for x in design) for b in range(width)] for a in range(width)]
    right = [sum(x[a] * y for x, y in zip(design, target)) for a in range(width)]
    for i in range(width):
        pivot = max(range(i, width), key=lambda r: abs(left[r][i]))
        left[i], left[pivot] = left[pivot], left[i]
        right[i], right[pivot] = right[pivot], right[i]
        if not left[i][i]:
            continue
        for r in range(width):
            if r == i:
                continue
            factor = left[r][i] / left[i][i]
            for c in range(i, width):
                left[r][c] -= factor * left[i][c]
            right[r] -= factor * right[i]
    return [right[i] / left[i][i] if left[i][i] else 0.0 for i in range(width)]


def apply(beta, row, features):
    return beta[0] + sum(b * row[f] for b, f in zip(beta[1:], features))


def correlation(a, b):
    mean_a, mean_b = statistics.mean(a), statistics.mean(b)
    top = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    bottom = math.sqrt(sum((x - mean_a) ** 2 for x in a) * sum((y - mean_b) ** 2 for y in b))
    return top / bottom if bottom else 0.0


def leave_one_season_out(rows, features):
    """Score by predicting each season from a model fitted on the others.

    A single held-out season is 30-odd clubs, which moves enough between draws
    to say anything you like. Pooling every season's held-out predictions and
    scoring them once is the same amount of data with none of the choice about
    which year to report.
    """
    usable = [r for r in rows if all(f in r for f in features)]
    predictions, truth = [], []
    for year in sorted({r["year"] for r in usable}):
        train = [r for r in usable if r["year"] != year]
        beta = fit(train, features)
        for row in [r for r in usable if r["year"] == year]:
            predictions.append(apply(beta, row, features))
            truth.append(row["result"])
    if not truth:
        return None
    baseline = math.sqrt(statistics.mean(t ** 2 for t in truth))
    error = math.sqrt(statistics.mean((p - t) ** 2 for p, t in zip(predictions, truth)))
    return {
        "n": len(truth), "baseline": baseline, "rmse": error,
        "gain": (baseline - error) / baseline if baseline else 0.0,
        "r": correlation(predictions, truth),
    }


#: The models worth printing, in the order that makes the comparison land: what
#: the table alone is worth, what the squad list alone is worth, then both.
MODELS = [
    ("last season's table", ["previous"]),
    ("last season's table + the division change", ["previous", "step"]),
    ("the squad list alone", ["pedigree_z"]),
    ("the squad list + academy share", ["pedigree_z", "youth_z"]),
    ("table + division change + squad list", ["previous", "step", "pedigree_z"]),
    ("all four", ["previous", "step", "pedigree_z", "youth_z"]),
]


def evaluate(rows, models=None):
    """Every model over the clubs that have a previous season, and the ones that do not.

    Two populations, because the interesting comparison and the interesting
    application are not the same set of clubs. Anything using last season needs
    a club to have had one; the squad list works on a club that has just been
    promoted into the division or has never appeared before, which is 50 more
    club-seasons and exactly the case where a forecast is worth having.
    """
    models = models or MODELS
    with_previous = [r for r in rows if "previous" in r]
    scored = []
    for label, features in models:
        result = leave_one_season_out(with_previous, features)
        if result:
            scored.append(dict(result, label=label, features=features))
    squad_only = []
    for label, features in models:
        if any(f in ("previous", "step") for f in features):
            continue
        result = leave_one_season_out(rows, features)
        if result:
            squad_only.append(dict(result, label=label, features=features))
    return {"with_previous": scored, "every_club": squad_only,
            "n_with_previous": len(with_previous), "n_all": len(rows)}


def preseason_table(rows, year, level=1, features=("previous", "step", "pedigree_z")):
    """One division's clubs ranked as they would have been before kick-off.

    The model is fitted without the season being ranked, so this is what the
    squad list said in advance rather than a description of what happened.
    """
    features = list(features)
    train = [r for r in rows if r["year"] != year and all(f in r for f in features)]
    if not train:
        return []
    beta = fit(train, features)
    table = [
        dict(row, predicted=apply(beta, row, features))
        for row in rows
        if row["year"] == year and row["level"] == level and all(f in row for f in features)
    ]
    return sorted(table, key=lambda r: -r["predicted"])


def by_move(rows):
    """How well each signal predicts, split by whether the club changed division.

    The point of the split is that the two signals do not degrade together. A
    club's own last table is a description of a division it is no longer in;
    the squad list describes players who are still there.
    """
    groups = {1: "promoted", -1: "relegated", 0: "stayed"}
    out = []
    for step, label in groups.items():
        group = [r for r in rows if r.get("step") == step]
        if len(group) < 5:
            continue
        out.append({
            "move": label, "n": len(group),
            "last_table": correlation([r["previous"] for r in group],
                                      [r["result"] for r in group]),
            "squad_list": correlation([r["pedigree_z"] for r in group],
                                      [r["result"] for r in group]),
        })
    return out


def division_pedigree(rows):
    """Championship and academy share by division and season.

    A validity check rather than a result. The measure is never told which
    division a club is in, so if it orders the divisions correctly on its own,
    it is measuring playing standard rather than noise.
    """
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["year"], row["level"])].append(row)
    return [
        {"year": year, "level": level, "clubs": len(group),
         "pedigree": statistics.mean(r["pedigree"] for r in group),
         "champions": statistics.mean(r["champions"] for r in group),
         "youth": statistics.mean(r["youth"] for r in group)}
        for (year, level), group in sorted(grouped.items(), key=lambda kv: (kv[0][0], kv[0][1] or 9))
        if level
    ]
