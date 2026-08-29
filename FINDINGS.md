# Findings

*[日本語版](FINDINGS.ja.md)*

Six things the Tokyo University Football Association's own pages do not show,
taken from five seasons of its published match records.

The federation publishes fixtures, a league table and a top-scorers list. The
records underneath hold per-player shot counts, lineups, timed substitutions and
coded cards. None of it is aggregated anywhere, and nothing below required data
the federation does not already put on its website — only reading it back across
seasons and dividing by the right denominator.

Everything here describes teams, divisions and year groups. Nothing describes an
individual; [the last section](#what-is-not-in-this-document) explains why that
is a deliberate limit rather than a gap.

## The dataset

Every league and cup competition the federation still publishes, as of August
2026.

| Season | Series | Fixtures | Appearances | Shot rows | Substitutions |
|---|---|---|---|---|---|
| 2026 | 4 | 350 | 6,633 | 8,564 | 1,720 |
| 2025 | 6 | 370 | 10,979 | 14,062 | 2,892 |
| 2024 | 6 | 426 | 12,451 | 15,795 | 3,227 |
| 2023 | 5 | 409 | 11,603 | 14,990 | 2,888 |
| 2022 | 5 | 410 | 11,396 | 13,611 | 2,915 |
| 2021 | 8 | 347 | 31 | 36 | 9 |

2,312 fixtures, 53,093 appearances, 3.56 million player-minutes, 7,748 goals,
6,499 players across 53 clubs.

## Reading the numbers

Three things change how the figures below should be read.

**Minutes are reconstructed.** The federation records a starting eleven, a bench
and timed substitutions, and never a minutes-played figure. Every per-90 number
here is derived from those three, including the correction for players sent off,
who leave the pitch at the minute of the red card and are otherwise credited with
a full match.

**Player-level recording starts in 2022.** 2021 has results and nothing else. A
handful of stray appearance rows survive the schema change — enough, if taken at
face value, to produce a conversion rate of 30.9 — so per-minute figures are
withheld for that season rather than computed from a rounding error.

**2026 was about 60% played** when this was written. It appears in the tables and
is drawn faintly in the charts, and it is excluded from the promotion and
relegation averages.

## 1. Promotion costs a point a game. Relegation gives back half

![Points per game before and after a division change](docs/figures/fig-promotion.png)

Promotion and relegation are the one natural experiment this dataset offers: the
same squad, one season later, against different opposition. Fifty-seven completed
cases across five seasons.

| | Cases | Change in points per game | Got worse |
|---|---|---|---|
| Promoted | 27 | **−1.04** | **26 of 27** |
| Relegated | 30 | **+0.53** | 9 of 30 |

Twenty-six of twenty-seven promoted sides did worse the following season. The one
exception went from 1.50 to 1.65 points per game moving from the third division
to the second in 2022 — the shallowest step available.

The asymmetry is the interesting part. If a division change were simply a change
of difficulty, going up and coming down would cost and return roughly the same
amount. They do not: promotion takes a full point per game and relegation returns
half of it, and three relegated sides in ten kept falling.

## 2. Year groups have no structure beyond "fourth years score"

![Minutes share and scoring rate by academic year](docs/figures/fig-grades.png)

Goals per 90 minutes by academic year, first division only. Pooling divisions
mixes populations, so this stays inside one of them.

| | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| 1st year | 0.086 | 0.118 | 0.044 | 0.122 | 0.118 |
| 2nd year | 0.140 | 0.120 | 0.126 | **0.074** | 0.146 |
| 3rd year | 0.128 | 0.124 | 0.161 | **0.169** | **0.117** |
| 4th year | 0.167 | 0.136 | 0.167 | 0.148 | **0.178** |

The 2026 third years score at 0.117, the lowest third-year figure in five
seasons. Read alone that looks like a story about the third year of a degree. It
is not: the 2025 third years were the *best* group on the table at 0.169, and the
dip that season belonged to the second years. Whichever year group looks weak
changes annually, which is what a cohort effect looks like and not what a
structural one looks like.

Only the fourth years are consistent, top of the table in three seasons of five
and never bottom. This is a negative result, and it is the reason a single season
is not enough to publish a claim about year groups.

One real change: first years took 9.5% of first-division minutes in 2026, against
5.5% in 2024. The highest share since 2022.

## 3. League position and shot volume are only loosely related

![League position against shot volume](docs/figures/fig-bubbles.png)

Rank on the x axis, shots per game on the y, total goals as circle area. Five of
twelve first-division sides in 2026 sit at least three places away from their
shot-volume rank.

| Team | Position | Shot-volume rank | Shots/game | Conversion |
|---|---|---|---|---|
| 横浜国立大学 | 7 | **4** | 12.5 | 0.110 |
| 武蔵大学 | 8 | **5** | 11.8 | 0.143 |
| 玉川大学 | 10 | **7** | 9.1 | 0.102 |
| 大東文化大学 | 5 | 8 | 8.7 | 0.204 |
| 朝鮮大学校 | 6 | 9 | 8.6 | 0.116 |

The top three do both — they shoot most and score most, so the axes agree. Below
that the table sorts on conversion, not volume. Yokohama National shoot as often
as the third-placed side and convert at half the rate; Daito Bunka shoot least in
the top half and finish at 0.204.

## 4. Squad character has a shape

![Team fingerprints](docs/figures/fig-fingerprints.png)

Six indices per team, each scaled within the season: shot volume, finishing,
defence, rotation (minutes spread beyond a settled eleven), youth (share of
minutes played by first and second years) and late push (share of shots in the
second half). Twelve small radars make squad character something you recognise by
outline rather than read off a table.

The extremes of each axis in 2026 belong to six different clubs:

| Axis | Highest | Lowest |
|---|---|---|
| Shot volume | 桜美林大学 (2nd) | 神奈川工科大学 (12th) |
| Finishing | 学習院大学 (4th) | 神奈川工科大学 (12th) |
| Defence | 帝京大学 (3rd) | 神奈川工科大学 (12th) |
| Rotation | 大東文化大学 (5th) | 横浜国立大学 (7th) |
| Youth | 武蔵大学 (8th) | 桜美林大学 (2nd) |
| Late push | 帝京大学 (3rd) | 朝鮮大学校 (6th) |

Only the bottom club is extreme on more than two axes, and only in the obvious
direction. The rest of the axes have nothing to do with finishing position:
Yokohama National are the most settled side in the division in seventh, Daito
Bunka the most rotated in fifth, Musashi the youngest in eighth.

## 5. Conversion rises as the division falls, except in the second

![Conversion by division over time](docs/figures/fig-conversion.png)

| | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| 1部 | 0.167 | 0.147 | 0.177 | 0.165 | 0.150 |
| 2部 | 0.173 | 0.189 | 0.182 | **0.145** | **0.142** |
| 3部 | – | – | – | 0.198 | 0.186 |
| チャレンジ | 0.233 | 0.214 | 0.207 | 0.187 | – |

Weaker defences concede more of the chances they face, so the deeper divisions
finish at higher rates — Challenge League converted at 0.233 in 2022 against
0.167 in the first division. The third division holds the pattern in both seasons
it exists here.

The second division does not. It sat above the first division for three seasons
and then crossed under it in 2025 and stayed there. The 2024 second division ran
nineteen teams against the usual ten to twelve, so a restructuring is the obvious
suspect, but this dataset cannot show it and the claim is left open.

## 6. A club can cross three tiers in five years

![Oubirin's trajectory](docs/figures/fig-trajectory.png)

桜美林大学: second division in 2021 (11 points), Challenge League in 2022, then
**13 wins from 13** in the 2023 Challenge League, second-division champions in
2024, first division in 2025, and second in the first division in 2026.

Club identity is stable across divisions in the federation's own data, so a
trajectory like this needs no name matching. It is also the reason a single
season's table says so little about a programme: three of the twelve sides in the
2026 first division were in a lower division two years earlier.

## What is not in this document

The most striking single number in the 2026 first division belongs to a player,
not a team: 7.34 shots per 90 minutes, roughly twice the next highest, from
someone who started six of thirteen appearances. A goals ranking cannot see them
at all.

They are not named here, and neither is anyone else.

The people in these records are amateur students. The federation publishes their
names because it runs the competition; that is not the same as a third party
republishing them. Per-player rows are personal data, and removing the name does
not fix it: of 189 first-division players above 270 minutes, 105 are unique on
team, position and appearances alone — three ordinary analytical columns, against
squad lists the federation already publishes.

So this document contains group statistics only, which is a different legal
object entirely. Everything player-level runs locally, on a database this
repository does not ship. [docs/DATA_POLICY.md](docs/DATA_POLICY.md) has the full
reasoning and the measurements.

## Related documents

- [docs/SEASON_TRENDS.md](docs/SEASON_TRENDS.md) — every table behind sections 1, 2, 5 and 6,
  including all 57 division changes and every club's path through the tiers.
- [docs/seasons/](docs/seasons/) — one document per season and division, 2021–2026.
- [docs/PLAYER_ANALYSIS_SAMPLE.md](docs/PLAYER_ANALYSIS_SAMPLE.md) — what the player-level
  output looks like, over an invented season.

## Reproducing

```bash
pip install .
togakuren ingest                                 # about 40 seconds
togakuren trends                                 # sections 1, 2, 5, 6
togakuren dashboard --series "2026 1部"          # sections 3, 4
togakuren privacy-check --series "2026 1部"      # the last section
togakuren trends --format md                     # docs/SEASON_TRENDS.md
togakuren profiles --all                         # docs/seasons/
```

The figures here are the charts from those two pages, `trends` and `dashboard
--privacy aggregate`, isolated and cropped. No number in this document was typed
in by hand.
