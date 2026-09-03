# The competition changed three times inside this dataset

*[日本語](LEAGUE_STRUCTURE.ja.md)*

Everything else here compares seasons with each other. That only means something
if the seasons are seasons of the same competition, and between 2021 and 2026
they are not. The league was rebuilt three times, and once it stopped being the
same league altogether.

This document is the correction. It is not a footnote to the other results — it
changed one of them and retracted another.

## What ran, year by year

Read off the federation's own series records.

| Season | Competition | Divisions (clubs) |
|---|---|---|
| 2021 | 東京都大学サッカーリーグ戦 (54th) | 1部 (13) · 2部 (10) · 3部 (10) · 4部 (8) |
| 2022 | 東京都大学サッカーリーグ戦 (55th) | 1部 (12) · 2部 (11) · チャレンジ (16) |
| 2023 | **関東大学サッカーリーグ戦 東京・神奈川 (1st)** | 1部 (12) · 2部 (12) · チャレンジ (14) |
| 2024 | 関東大学サッカーリーグ戦 東京・神奈川 (2nd) | 1部 (12) · **2部 (19)** · チャレンジ (9) |
| 2025 | 関東大学サッカーリーグ戦 東京・神奈川 (3rd) | 1部 (12) · 2部 (10) · **3部 (9)** · チャレンジ (6) |
| 2026 | 関東大学サッカーリーグ戦 東京・神奈川 (4th) | 1部 (12) · 2部 (10) · 3部 (15) |

Three rebuilds and one change of identity:

**2022 — four divisions became three.** The third and fourth divisions were
merged into a Challenge League. Seven clubs from the fourth division and six
from the third arrived in the same competition.

**2023 — the Tokyo league stopped existing.** It merged with the Kanagawa
prefectural university league and was reconstituted as the Tokyo/Kanagawa
division of the Kanto league. Seven clubs joined, six of them from Kanagawa; and
eight left, six of them out of the first division. In the same year the Kanto
league above it went to three divisions of its own, so the promotion and
relegation quota out of the top of this league now varies with how many clubs
move between it and Kanto's third division.

**2025 — a third division was inserted above the Challenge League**, which had
been the third level since 2022 and became the fourth. Seven clubs went into it
from a second division that was being cut from nineteen back to ten, and two
came up from the Challenge League.

**2026 — the Challenge League was abolished** and its remaining clubs went into
the third division, which grew from nine to fifteen.

## The Challenge League's level is not in its name

Every other division carries its level: 1部 is the first, 2部 the second. The
Challenge League carries nothing, and it sat at the third level in 2022–2024 and
the fourth in 2025.

This repository originally read levels off a fixed map that put the Challenge
League at 5 in every year. That is not a labelling nicety. It reverses
directions:

- Seven clubs that went **up** from the 2021 fourth division into the 2022
  Challenge League were recorded as relegated.
- Six clubs that moved **sideways** from the 2021 third division into the same
  Challenge League were recorded as relegated too.
- Two clubs that stayed at the **same** level from the 2024 Challenge League
  into the 2025 third division were recorded as promoted.

Fifteen of seventy-two division changes had the wrong direction — 21%.

`analysis.season_ladder` now derives the level from the divisions that actually
ran: numbered divisions keep their number, and the Challenge League sits one
below the deepest numbered division of that season.

## What the correction did to the published figures

`division_moves` also now carries `moved`, which is false for the five Challenge
League clubs that lost a level in 2025 without changing division or playing a
match. A reorganisation is not a relegation, and those five are excluded from
the averages below.

| | As published | Corrected |
|---|---|---|
| Promoted | 27 cases, **−1.04** ppg, 26 of 27 worse | 32 cases, **−0.97** ppg, 29 of 32 worse |
| Relegated | 30 cases, **+0.53** ppg, 9 of 30 worse | 17 cases, **+1.24** ppg, 1 of 17 worse |

**The promotion result survives.** −1.04 becomes −0.97 and the unanimity holds:
twenty-nine of thirty-two promoted sides did worse. It also holds inside each
boundary separately, which is the point — if it were an artefact of the
reorganisations it would not.

| Promotions at | Cases | Change |
|---|---|---|
| the 2022 restructure | 12 | −0.96 |
| the 2023 merge | 8 | −0.94 |
| the 2025 third division | 3 | −1.18 |
| boundaries where the ladder did not move | 9 | −0.95 |

**The asymmetry is retracted.** The claim was that promotion costs a point a
game and relegation returns only half of it, and that three relegated sides in
ten keep falling. Both halves came from the mislabelled cases: thirteen clubs
that had gone level or up in 2022 were sitting in the relegated column, and they
had not improved. With them removed, relegation returns **+1.24** — more than
promotion costs, not half — and **one** relegated side in seventeen got worse,
not nine in thirty.

## How big the 2023 discontinuity is

The only thing that crosses the boundary is a club that played the same division
in both years. Mean points per game of the clubs that stayed put:

| | 2021→22 | **2022→23** | 2023→24 | 2024→25 | 2025→26 * |
|---|---|---|---|---|---|
| 1部 | +0.09 (n=9) | **+0.83 (n=6)** | −0.22 (n=9) | +0.00 (n=9) | −0.23 (n=9) |
| 2部 | +0.23 (n=6) | **+0.59 (n=6)** | +0.11 (n=9) | −0.31 (n=8) | −0.57 (n=5) |

\* 2026 is about 60% played.

A first-division club that did nothing at all gained **0.83 points a game** in
2023 — five to six times the movement at any other boundary. Six of the twelve
first-division clubs had left for the Kanto league proper, and there were no
relegations from the first division that year: five clubs came up from the
second division to backfill. The clubs that stayed were the bottom half of the
old first division, and against the new field they nearly doubled their points.

**Nothing that compares a club's 2022 with its 2023 is measuring football.** The
same applies to any level-wide average read across that boundary.

## Where this still needs work

- `docs/SEASON_TRENDS.en.md`, `docs/PREDICTION.en.md` and `docs/LEAGUE_COMPARISON.en.md`
  all pool seasons. The forecasting model's 180-day half-life discounts the
  2022 season heavily by the time it is predicting 2023 onwards, which limits
  the damage but does not measure it; nobody has checked what the merge does to
  the backtest.
- The 2024 second division of nineteen clubs is now explained — it was the
  staging year before the third division was created — but the conversion-rate
  anomaly in the second division from 2025 onwards, noted in `FINDINGS.en.md`, is
  still unexplained.
- The 2021 third and fourth divisions are incomplete in the source: 44 fixtures
  for ten clubs and 23 for eight, and the fourth division records no draws at
  all. They are used for division changes into 2022 and for nothing else.

## Sources

- Federation series records, this dataset.
- [関東大学サッカーリーグが3部制に](https://web.gekisaka.jp/news/university/detail/?354357-354357-fl) — the Kanto league's own move to three divisions from 2023.
- [「2023年度 第1回 関東大学サッカーリーグ東京・神奈川」開催決定およびリーグ編成のお知らせ](https://www.f-togakuren.com/archives/5517) — the federation's announcement of the merger.
- [東京都大学サッカーリーグ — Wikipedia](https://ja.wikipedia.org/wiki/%E6%9D%B1%E4%BA%AC%E9%83%BD%E5%A4%A7%E5%AD%A6%E3%82%B5%E3%83%83%E3%82%AB%E3%83%BC%E3%83%AA%E3%83%BC%E3%82%B0) — season-by-season composition, and that the promotion quota varies with movement to and from Kanto's third division.
