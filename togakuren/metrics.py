"""Aggregations over the loaded fixtures.

The federation publishes a goals ranking and nothing else. Every function here
answers a question that ranking cannot: who shoots most for the time they are
actually on the pitch, who converts, when in a match a team's shots arrive.
"""

PLAYER_SEASON = """
WITH played AS (
    SELECT a.player_id,
           gt.team_pk,
           COUNT(*)                                        AS apps,
           SUM(a.role = 'start')                           AS starts,
           SUM(a.minutes)                                  AS minutes
    FROM appearances a
    JOIN game_teams gt ON gt.id = a.game_team_id
    JOIN games g       ON g.id = gt.game_id
    WHERE gt.series_id = :series_id AND g.game_over = 1
    GROUP BY a.player_id, gt.team_pk
),
shooting AS (
    SELECT a.player_id, gt.team_pk,
           SUM(s.total)    AS shots,
           SUM(s.first_half) AS h1, SUM(s.second_half) AS h2,
           SUM(s.extra_first) AS e1, SUM(s.extra_second) AS e2
    FROM shots s
    JOIN appearances a ON a.game_team_id = s.game_team_id AND a.player_id = s.player_id
    JOIN game_teams gt ON gt.id = s.game_team_id
    JOIN games g       ON g.id = gt.game_id
    WHERE gt.series_id = :series_id AND g.game_over = 1
    GROUP BY a.player_id, gt.team_pk
),
main_position AS (
    -- A player can be listed in several roles across a season; take the one
    -- they spent most minutes in, and fall back to it when the squad list has
    -- no position (players registered mid-season are sometimes missing).
    SELECT player_id, team_pk, position FROM (
        SELECT a.player_id, gt.team_pk, a.position,
               ROW_NUMBER() OVER (
                   PARTITION BY a.player_id, gt.team_pk ORDER BY SUM(a.minutes) DESC
               ) AS rank
        FROM appearances a
        JOIN game_teams gt ON gt.id = a.game_team_id
        WHERE gt.series_id = :series_id AND a.position IS NOT NULL AND a.position <> ''
        GROUP BY a.player_id, gt.team_pk, a.position
    ) WHERE rank = 1
),
scoring AS (
    SELECT e.player_id, gt.team_pk,
           SUM(e.type = 'goal')   AS goals,
           SUM(e.type = 'yellow') AS yellows,
           SUM(e.type = 'red')    AS reds
    FROM events e
    JOIN game_teams gt ON gt.id = e.game_team_id
    JOIN games g       ON g.id = gt.game_id
    WHERE gt.series_id = :series_id AND g.game_over = 1
    GROUP BY e.player_id, gt.team_pk
)
SELECT played.player_id,
       t.short_name                                        AS team,
       COALESCE(sm.position, main_position.position, '')   AS position,
       sm.grade                                            AS grade,
       played.apps, played.starts, played.minutes,
       COALESCE(shooting.shots, 0)                         AS shots,
       COALESCE(scoring.goals, 0)                          AS goals,
       COALESCE(scoring.yellows, 0)                        AS yellows,
       COALESCE(scoring.reds, 0)                           AS reds,
       COALESCE(shooting.h1, 0) AS first_half, COALESCE(shooting.h2, 0) AS second_half
FROM played
LEFT JOIN shooting ON shooting.player_id = played.player_id AND shooting.team_pk = played.team_pk
LEFT JOIN scoring  ON scoring.player_id  = played.player_id AND scoring.team_pk  = played.team_pk
LEFT JOIN teams t  ON t.id = played.team_pk
LEFT JOIN squad_members sm
       ON sm.player_id = played.player_id AND sm.team_pk = played.team_pk
LEFT JOIN main_position
       ON main_position.player_id = played.player_id AND main_position.team_pk = played.team_pk
WHERE played.minutes >= :min_minutes
"""

TEAM_SEASON = """
SELECT t.id                                AS team_pk,
       t.short_name                        AS team,
       COUNT(DISTINCT gt.id)               AS played,
       SUM(gt.score)                       AS goals_for,
       SUM(shot.total)                     AS shots,
       SUM(shot.h1) AS first_half, SUM(shot.h2) AS second_half,
       st.points, st.win, st.draw, st.lose, st.goal_difference
FROM game_teams gt
JOIN games g  ON g.id = gt.game_id AND g.game_over = 1
JOIN teams t  ON t.id = gt.team_pk
LEFT JOIN standings st ON st.team_pk = t.id
LEFT JOIN (
    SELECT game_team_id,
           SUM(total)    AS total,
           SUM(first_half) AS h1, SUM(second_half) AS h2
    FROM shots GROUP BY game_team_id
) shot ON shot.game_team_id = gt.id
WHERE gt.series_id = :series_id
GROUP BY t.id
ORDER BY st.points DESC, st.goal_difference DESC
"""


def _per90(value, minutes):
    return round(value * 90 / minutes, 2) if minutes else 0.0


def player_season(conn, series_id, min_minutes=270, order_by="shots_per_90"):
    """Per-player season totals plus the rate metrics derived from them.

    Args:
        min_minutes: minimum minutes played to appear. Rate metrics over tiny
            samples are noise; the default is three full matches.
        order_by: any key of the returned rows.
    """
    rows = []
    for row in conn.execute(PLAYER_SEASON, {"series_id": series_id, "min_minutes": min_minutes}):
        entry = dict(row)
        minutes, shots, goals = entry["minutes"], entry["shots"], entry["goals"]
        entry["shots_per_90"] = _per90(shots, minutes)
        entry["goals_per_90"] = _per90(goals, minutes)
        entry["conversion"] = round(goals / shots, 3) if shots else 0.0
        entry["minutes_per_app"] = round(minutes / entry["apps"], 1) if entry["apps"] else 0.0
        entry["sub_apps"] = entry["apps"] - entry["starts"]
        rows.append(entry)
    rows.sort(key=lambda item: item.get(order_by) or 0, reverse=True)
    return rows


def team_season(conn, series_id):
    """Per-team season totals, ordered by league position."""
    rows = []
    for row in conn.execute(TEAM_SEASON, {"series_id": series_id}):
        entry = dict(row)
        shots = entry["shots"] or 0
        entry["shots"] = shots
        entry["shots_per_game"] = round(shots / entry["played"], 1) if entry["played"] else 0.0
        entry["conversion"] = round((entry["goals_for"] or 0) / shots, 3) if shots else 0.0
        rows.append(entry)
    return rows


def shot_periods(conn, series_id):
    """League-wide shot distribution across halves and extra time."""
    row = conn.execute(
        """
        SELECT SUM(s.first_half), SUM(s.second_half),
               SUM(s.extra_first), SUM(s.extra_second)
        FROM shots s
        JOIN game_teams gt ON gt.id = s.game_team_id
        JOIN games g       ON g.id = gt.game_id AND g.game_over = 1
        WHERE gt.series_id = :series_id
        """,
        {"series_id": series_id},
    ).fetchone()
    return [value or 0 for value in row]


def goal_minutes(conn, series_id, bucket=15):
    """Goals bucketed by minute, for a scoring-timeline chart."""
    counts = {}
    for (minute,) in conn.execute(
        """
        SELECT e.minute FROM events e
        JOIN game_teams gt ON gt.id = e.game_team_id
        JOIN games g       ON g.id = gt.game_id AND g.game_over = 1
        WHERE gt.series_id = :series_id AND e.type = 'goal' AND e.minute IS NOT NULL
        """,
        {"series_id": series_id},
    ):
        key = min(int(minute) // bucket, 90 // bucket - 1) * bucket
        counts[key] = counts.get(key, 0) + 1
    return [(start, counts.get(start, 0)) for start in range(0, 90, bucket)]


def substitution_profile(conn, series_id):
    """When each team makes its changes — a cheap proxy for bench usage."""
    rows = []
    for row in conn.execute(
        """
        SELECT t.short_name AS team,
               COUNT(*) AS subs,
               ROUND(AVG(s.minute), 1) AS mean_minute,
               COUNT(DISTINCT s.in_player_id) AS players_used
        FROM substitutions s
        JOIN game_teams gt ON gt.id = s.game_team_id
        JOIN games g       ON g.id = gt.game_id AND g.game_over = 1
        JOIN teams t       ON t.id = gt.team_pk
        WHERE gt.series_id = :series_id AND s.minute IS NOT NULL
        GROUP BY t.id ORDER BY mean_minute
        """,
        {"series_id": series_id},
    ):
        rows.append(dict(row))
    return rows


def series_list(conn):
    """Every loaded series with its fixture count."""
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT s.id, s.year, s.name, s.short_name,
                   COUNT(g.id) AS games,
                   SUM(g.game_over) AS completed
            FROM series s LEFT JOIN games g ON g.series_id = s.id
            GROUP BY s.id ORDER BY s.year DESC, s.short_name
            """
        )
    ]
