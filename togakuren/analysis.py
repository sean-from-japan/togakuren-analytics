"""Team-level analysis: profiles, fingerprints, rotation and history.

:mod:`metrics` answers "how did this player do". This module answers "what kind
of team is this" — which needs the same records read along different axes:
against whom, with which year groups, spread across how many players, and how
that changed between seasons and divisions.
"""

from collections import defaultdict

GRADES = ("1", "2", "3", "4")

#: The six axes of :func:`fingerprints`, in display order.
FINGERPRINT_AXES = (
    ("volume", "Shot volume", "Shots per game"),
    ("finishing", "Finishing", "Goals per shot"),
    ("defence", "Defence", "Fewer goals conceded per game"),
    ("rotation", "Rotation", "Minutes spread beyond a settled eleven"),
    ("youth", "Youth", "Share of minutes played by 1st and 2nd years"),
    ("late", "Late push", "Share of shots taken in the second half"),
)

TEAM_PROFILE = """
WITH results AS (
    SELECT gt.team_pk,
           COUNT(*)                          AS played,
           SUM(gt.score)                     AS goals_for,
           SUM(opp.score)                    AS goals_against,
           SUM(gt.points)                    AS points,
           SUM(gt.fairplay_points)           AS fairplay_points
    FROM game_teams gt
    JOIN games g      ON g.id = gt.game_id AND g.game_over = 1
    JOIN game_teams opp ON opp.game_id = gt.game_id AND opp.id <> gt.id
    WHERE gt.series_id = :series_id
    GROUP BY gt.team_pk
),
shooting AS (
    SELECT gt.team_pk,
           SUM(s.total)       AS shots,
           SUM(s.first_half)  AS first_half,
           SUM(s.second_half) AS second_half
    FROM shots s
    JOIN game_teams gt ON gt.id = s.game_team_id
    JOIN games g       ON g.id = gt.game_id AND g.game_over = 1
    WHERE gt.series_id = :series_id
    GROUP BY gt.team_pk
),
usage AS (
    SELECT gt.team_pk,
           COUNT(DISTINCT a.player_id) AS players_used,
           SUM(a.minutes)              AS minutes
    FROM appearances a
    JOIN game_teams gt ON gt.id = a.game_team_id
    JOIN games g       ON g.id = gt.game_id AND g.game_over = 1
    WHERE gt.series_id = :series_id
    GROUP BY gt.team_pk
),
subs AS (
    SELECT gt.team_pk, AVG(sb.minute) AS mean_sub_minute, COUNT(*) AS sub_count
    FROM substitutions sb
    JOIN game_teams gt ON gt.id = sb.game_team_id
    JOIN games g       ON g.id = gt.game_id AND g.game_over = 1
    WHERE gt.series_id = :series_id AND sb.minute IS NOT NULL
    GROUP BY gt.team_pk
)
SELECT t.id AS team_pk, t.team_id, t.short_name AS team,
       results.played, results.points, results.goals_for, results.goals_against,
       results.fairplay_points,
       COALESCE(shooting.shots, 0) AS shots,
       COALESCE(shooting.first_half, 0) AS first_half,
       COALESCE(shooting.second_half, 0) AS second_half,
       usage.players_used, usage.minutes,
       subs.mean_sub_minute, subs.sub_count
FROM teams t
JOIN results  ON results.team_pk = t.id
LEFT JOIN shooting ON shooting.team_pk = t.id
LEFT JOIN usage    ON usage.team_pk = t.id
LEFT JOIN subs     ON subs.team_pk = t.id
WHERE t.series_id = :series_id
"""


def _player_minutes(conn, series_id):
    """Minutes per player per team, most-used first."""
    grouped = defaultdict(list)
    for team_pk, player_id, minutes in conn.execute(
        """
        SELECT gt.team_pk, a.player_id, SUM(a.minutes)
        FROM appearances a
        JOIN game_teams gt ON gt.id = a.game_team_id
        JOIN games g       ON g.id = gt.game_id AND g.game_over = 1
        WHERE gt.series_id = :series_id
        GROUP BY gt.team_pk, a.player_id
        ORDER BY SUM(a.minutes) DESC
        """,
        {"series_id": series_id},
    ):
        grouped[team_pk].append((player_id, minutes))
    return grouped


def _grade_minutes(conn, series_id):
    """Minutes and goals by academic year, per team."""
    grouped = defaultdict(lambda: defaultdict(lambda: {"players": 0, "minutes": 0, "goals": 0}))
    for team_pk, grade, players, minutes in conn.execute(
        """
        SELECT gt.team_pk, sm.grade, COUNT(DISTINCT a.player_id), SUM(a.minutes)
        FROM appearances a
        JOIN game_teams gt   ON gt.id = a.game_team_id
        JOIN games g         ON g.id = gt.game_id AND g.game_over = 1
        JOIN squad_members sm ON sm.player_id = a.player_id AND sm.team_pk = gt.team_pk
        WHERE gt.series_id = :series_id
        GROUP BY gt.team_pk, sm.grade
        """,
        {"series_id": series_id},
    ):
        grouped[team_pk][grade or "?"].update(players=players, minutes=minutes or 0)
    for team_pk, grade, goals in conn.execute(
        """
        SELECT gt.team_pk, sm.grade, COUNT(*)
        FROM events e
        JOIN game_teams gt   ON gt.id = e.game_team_id
        JOIN games g         ON g.id = gt.game_id AND g.game_over = 1
        JOIN squad_members sm ON sm.player_id = e.player_id AND sm.team_pk = gt.team_pk
        WHERE gt.series_id = :series_id AND e.type = 'goal'
        GROUP BY gt.team_pk, sm.grade
        """,
        {"series_id": series_id},
    ):
        grouped[team_pk][grade or "?"]["goals"] = goals
    return grouped


def team_profile(conn, series_id):
    """One rich row per team, ordered by league position.

    Adds to the raw totals the things the league table cannot show: how
    concentrated the minutes are, which year groups played them, and when in a
    match the team shoots.
    """
    minutes_by_team = _player_minutes(conn, series_id)
    grades_by_team = _grade_minutes(conn, series_id)

    rows = []
    for record in conn.execute(TEAM_PROFILE, {"series_id": series_id}):
        row = dict(record)
        played = row["played"] or 0
        minutes = row["minutes"] or 0
        shots = row["shots"] or 0

        row["goal_difference"] = (row["goals_for"] or 0) - (row["goals_against"] or 0)
        row["shots_per_game"] = shots / played if played else 0.0
        row["conversion"] = (row["goals_for"] or 0) / shots if shots else 0.0
        row["conceded_per_game"] = (row["goals_against"] or 0) / played if played else 0.0
        halves = (row["first_half"] or 0) + (row["second_half"] or 0)
        row["second_half_share"] = (row["second_half"] or 0) / halves if halves else 0.0

        ordered = minutes_by_team.get(row["team_pk"], [])
        core = sum(value for _, value in ordered[:11])
        row["core_share"] = core / minutes if minutes else 0.0
        row["rotation"] = 1 - row["core_share"]
        # A "regular" plays at least half of the minutes available to them.
        available = minutes / 11 if minutes else 0
        row["regulars"] = sum(1 for _, value in ordered if available and value >= 0.5 * available)

        grades = grades_by_team.get(row["team_pk"], {})
        row["grades"] = {
            grade: dict(grades.get(grade, {"players": 0, "minutes": 0, "goals": 0}))
            for grade in GRADES
        }
        young = sum(row["grades"][grade]["minutes"] for grade in ("1", "2"))
        row["youth_share"] = young / minutes if minutes else 0.0
        weighted = sum(int(grade) * row["grades"][grade]["minutes"] for grade in GRADES)
        row["mean_grade"] = weighted / minutes if minutes else 0.0
        rows.append(row)

    rows.sort(key=lambda item: (-(item["points"] or 0), -item["goal_difference"], -(item["goals_for"] or 0)))
    for position, row in enumerate(rows, start=1):
        row["rank"] = position
    return rows


def _scale(values):
    """Map values onto 0-100 within the series. Flat inputs land mid-scale."""
    low, high = min(values), max(values)
    if high - low < 1e-12:
        return [50.0 for _ in values]
    return [100 * (value - low) / (high - low) for value in values]


def fingerprints(conn, series_id, profile=None):
    """Six comparable indices per team, each scaled against this series.

    The scaling is relative on purpose: the question is what distinguishes these
    teams from each other, not how they compare to professional football.
    """
    profile = profile or team_profile(conn, series_id)
    if not profile:
        return []

    raw = {
        "volume": [row["shots_per_game"] for row in profile],
        "finishing": [row["conversion"] for row in profile],
        # Conceding fewer is better, so invert before scaling.
        "defence": [-row["conceded_per_game"] for row in profile],
        "rotation": [row["rotation"] for row in profile],
        "youth": [row["youth_share"] for row in profile],
        "late": [row["second_half_share"] for row in profile],
    }
    scaled = {axis: _scale(values) for axis, values in raw.items()}

    return [
        {
            "team_pk": row["team_pk"],
            "team": row["team"],
            "rank": row["rank"],
            "axes": {axis: round(scaled[axis][index], 1) for axis, _, _ in FINGERPRINT_AXES},
        }
        for index, row in enumerate(profile)
    ]


def points_curve(conn, series_id):
    """Cumulative league points by matchday, per team."""
    running = defaultdict(int)
    series = defaultdict(list)
    rows = conn.execute(
        """
        SELECT gt.team_pk, t.short_name, CAST(g.section AS INTEGER) AS section, gt.points
        FROM game_teams gt
        JOIN games g  ON g.id = gt.game_id AND g.game_over = 1
        JOIN teams t  ON t.id = gt.team_pk
        WHERE gt.series_id = :series_id
        ORDER BY section, g.kickoff
        """,
        {"series_id": series_id},
    )
    names = {}
    for team_pk, name, section, points in rows:
        names[team_pk] = name
        running[team_pk] += points or 0
        series[team_pk].append((section, running[team_pk]))
    return [
        {"team_pk": team_pk, "team": names[team_pk], "points": values}
        for team_pk, values in series.items()
    ]


def goals_by_opponent(conn, series_id, profile=None):
    """Where a team's goals came from, split by the opponent's finishing rank.

    A side that scores freely against the bottom of the table and dries up
    against the top looks the same in the goals column as one that does the
    reverse.
    """
    profile = profile or team_profile(conn, series_id)
    if not profile:
        return []
    rank = {row["team_pk"]: row["rank"] for row in profile}
    half = len(profile) / 2

    tally = defaultdict(lambda: {"top": 0, "bottom": 0})
    for team_pk, opponent_pk, goals in conn.execute(
        """
        SELECT gt.team_pk, opp.team_pk, gt.score
        FROM game_teams gt
        JOIN games g        ON g.id = gt.game_id AND g.game_over = 1
        JOIN game_teams opp ON opp.game_id = gt.game_id AND opp.id <> gt.id
        WHERE gt.series_id = :series_id
        """,
        {"series_id": series_id},
    ):
        if opponent_pk not in rank:
            continue
        bucket = "bottom" if rank[opponent_pk] > half else "top"
        tally[team_pk][bucket] += goals or 0

    rows = []
    for row in profile:
        counts = tally[row["team_pk"]]
        total = counts["top"] + counts["bottom"]
        rows.append(
            {
                "team_pk": row["team_pk"],
                "team": row["team"],
                "rank": row["rank"],
                "vs_top": counts["top"],
                "vs_bottom": counts["bottom"],
                "bottom_share": counts["bottom"] / total if total else 0.0,
            }
        )
    return rows


def minutes_matrix(conn, series_id, team_pk):
    """Who played, in which matchday, for how long.

    Returns ``{"sections": [...], "players": [{player_id, position, total,
    starts, minutes: {section: value}}]}`` ordered by total minutes, which makes
    a settled side and a rotated one visibly different shapes.
    """
    sections = [
        int(row[0])
        for row in conn.execute(
            """
            SELECT DISTINCT CAST(g.section AS INTEGER)
            FROM games g JOIN game_teams gt ON gt.game_id = g.id
            WHERE gt.series_id = :series_id AND gt.team_pk = :team_pk AND g.game_over = 1
            ORDER BY 1
            """,
            {"series_id": series_id, "team_pk": team_pk},
        )
    ]

    players = {}
    for player_id, section, minutes, role, position in conn.execute(
        """
        SELECT a.player_id, CAST(g.section AS INTEGER), a.minutes, a.role, a.position
        FROM appearances a
        JOIN game_teams gt ON gt.id = a.game_team_id
        JOIN games g       ON g.id = gt.game_id AND g.game_over = 1
        WHERE gt.series_id = :series_id AND gt.team_pk = :team_pk
        """,
        {"series_id": series_id, "team_pk": team_pk},
    ):
        entry = players.setdefault(
            player_id,
            {"player_id": player_id, "position": position, "total": 0, "starts": 0, "minutes": {}},
        )
        entry["minutes"][section] = entry["minutes"].get(section, 0) + minutes
        entry["total"] += minutes
        if role == "start":
            entry["starts"] += 1
        if not entry["position"]:
            entry["position"] = position

    detail = {
        row[0]: {"grade": row[1], "number": row[2], "position": row[3]}
        for row in conn.execute(
            "SELECT player_id, grade, number, position FROM squad_members WHERE team_pk = ?",
            (team_pk,),
        )
    }
    for player_id, entry in players.items():
        extra = detail.get(player_id, {})
        entry["grade"] = extra.get("grade")
        entry["number"] = extra.get("number")
        entry["position"] = entry["position"] or extra.get("position")

    ordered = sorted(players.values(), key=lambda item: -item["total"])
    return {"sections": sections, "players": ordered}


def team_history(conn, team_id):
    """One club's league seasons, across divisions, oldest first.

    ``team_id`` is the federation-wide club id and is stable across seasons and
    divisions, so promotion and relegation show up as a change of division on
    consecutive rows. A missing year is not a gap in the data: clubs promoted out
    of this federation's leagues simply stop appearing until they return.

    Tournament group stages are excluded even though the CMS files some of them
    under ``type = "league"``.
    """
    rows = []
    for record in conn.execute(
        """
        SELECT s.year, s.short_name AS division, s.id AS series_id, t.id AS team_pk,
               st.played, st.win, st.draw, st.lose, st.points,
               st.goals_for, st.goal_difference
        FROM teams t
        JOIN series s     ON s.id = t.series_id
        LEFT JOIN standings st ON st.team_pk = t.id
        WHERE t.team_id = :team_id
          AND s.type = 'league'
          AND s.name NOT LIKE '%トーナメント%'
          AND st.played IS NOT NULL
        ORDER BY s.year, s.short_name
        """,
        {"team_id": team_id},
    ):
        row = dict(record)
        if row["played"]:
            row["points_per_game"] = round(row["points"] / row["played"], 2)
        rows.append(row)
    return rows
