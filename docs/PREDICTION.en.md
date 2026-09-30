# Forecasting

*[日本語](PREDICTION.ja.md)*

Every other document here describes what happened. This one makes claims about
what has not happened yet, so it is written to be checked rather than believed:
each model is scored against the class prior, on fixtures it has not seen, and
the settings were chosen on 2022–2024 and then left alone so that the 2025–2026
numbers below are out of sample.

```bash
togakuren backtest --league-only --until 2024   # the tuning window below
togakuren backtest --league-only --start 2025   # the held-out block below
togakuren forecast --series "2026 1部"          # the fixtures still to play
togakuren dashboard --series "2026 1部" --forecast   # the same forecast, club by club, as HTML
```

One thing is not accounted for below. The league merged with Kanagawa's in 2023
and the club pool changed with it, so the tuning window straddles a change of
competition ([LEAGUE_STRUCTURE.en.md](LEAGUE_STRUCTURE.en.md)). The 180-day half-life
happens to discount 2022 heavily by the time the model is predicting 2023
onwards, which limits the damage — but that is a coincidence of the setting, not
a correction, and nobody has measured what the merger does to these numbers.

## The models

| | |
|---|---|
| `prior` | The running frequency of the three outcomes. Everything else has to beat this. |
| `elo` | One rating per club, moved by result and margin. |
| `poisson` | Attack and defence strengths per club, fitted by weighted maximum likelihood, turned into a scoreline distribution. |

The Poisson fit is coordinate ascent with a closed form for every parameter, so
this adds no dependency to a tool that has none.

## How it is scored

Walk-forward, always: each fixture is predicted using only fixtures played before
it, then handed to the models. A shuffled hold-out would leak the future — team
strength in March tells you about January — and would flatter every model here.
One test in the suite exists purely to assert that a model is never shown a
fixture before it predicts it.

Primary metric is multiclass log loss in nats; lower is better, and the prior is
the number to beat. Accuracy is reported because it is legible, not because it is
informative: a model can gain accuracy by rounding every close fixture towards
the favourite while getting worse at everything that matters.

What those names mean. **Log loss** scores how much probability a model put on
the result that actually happened, and grows the more confidently it is wrong, so
lower is better. **Nats** is its unit when natural logs are used: losing 0.102
nats is putting about 10% less probability on what happened. **Brier** scores the
same forecasts as a squared error, runs from 0 to 2, and is also better lower.
**Prior** is the model that predicts the running frequency of home win, draw and
away win and nothing else — failing to beat it means the fitting bought nothing.
**n** in the tables is a number of fixtures.

## Results

League fixtures only. Settings were chosen on the first block and not revisited.

**Tuning window, 2022–2024 (n = 1,090)**

| model | log loss | Brier | accuracy |
|---|---|---|---|
| prior | 1.0090 | 0.6150 | 42.0% |
| elo | 0.8650 | 0.5022 | 62.9% |
| poisson | 0.8311 | 0.4779 | 66.3% |

**Held out, 2025–2026 (n = 597, fixtures up to 2026-09-27)**

| model | log loss | Brier | accuracy |
|---|---|---|---|
| prior | 1.0174 | 0.6190 | 44.9% |
| elo | 0.8672 | 0.5042 | 61.6% |
| **poisson** | **0.8211** | **0.4748** | **65.7%** |

The prior is high here for a football league because draws are rare: 15.4% of the
2,256 finished fixtures, against roughly a quarter in professional football. Two
university sides are less likely to be evenly matched than two professional ones,
which is the same reason the model gets as far as it does.

## What actually mattered

Each row removes one thing from the full model. Held-out 2025–2026 league fixtures.

| variant | log loss | change |
|---|---|---|
| poisson | 0.8211 | — |
| without the Dixon-Coles term | 0.8238 | +0.003 |
| without the home term | 0.8312 | +0.010 |
| **without time decay** | **0.9227** | **+0.102** |

**Time decay is the whole game.** A model that weights a fixture from four years
ago the same as one from last month is worse than Elo. Weighting a fixture by a
180-day half-life is worth more than every other refinement here put together —
which is what a competition whose squads are rebuilt every April should look
like.

**How much of last season carries over did not replicate.** Elo has a parameter
for how far ratings are pulled back to the mean between seasons. On 2022–2024,
keeping half of a club's rating clearly beat both keeping all of it (0.8650
against 0.8918) and discarding it entirely (0.8681). On 2025–2026 the ordering
reversed: keeping all of it, the worst choice on the tuning block, was the best
(0.8606, against 0.8672 for half and 0.8709 for none). Two windows, two answers,
so there is no answer here — only the continuous decay above, which does hold up
across both.

## Home advantage

The API records a venue for each fixture and never a host, so home is inferred:
a ground used at least three times, with the same club involved in at least 75%
of those fixtures, is that club's. That identifies a host for **1,072 of the
2,256 finished fixtures**; the rest are treated as neutral, which many of them
genuinely are.

Where a host is identifiable, it wins 46.1%, draws 18.6% and loses 35.4% —
**1.568 points per game against 1.246**. The model fitted on 2026-09-28 puts the
effect at +15.9% on the scoring rate.

As a forecasting term it is worth less than that sounds: it applies to under half
the fixtures, it improved the held-out block by 0.010 nats, and on the tuning
block it was very slightly *negative*. It is kept because it is measurable in the
results and mechanically plausible, not because the forecast needs it.

## Calibration

Held-out 2025–2026 league fixtures, every outcome of every fixture as one point.

| predicted | n | mean predicted | observed |
|---|---|---|---|
| 0–10% | 234 | 5.1% | 5.6% |
| 10–20% | 534 | 16.2% | 15.7% |
| 20–30% | 271 | 23.8% | 23.6% |
| 30–40% | 156 | 35.2% | 30.1% |
| 40–50% | 150 | 44.9% | 47.3% |
| 50–60% | 148 | 55.0% | 58.8% |
| 60–70% | 103 | 65.3% | 65.0% |
| 70–80% | 78 | 74.6% | 75.6% |
| 80–90% | 65 | 85.2% | 86.2% |
| 90–100% | 52 | 95.1% | 94.2% |

Close to the diagonal where the data is thick. The 30–40% band is still the one
real miss — 35.2% predicted, 30.1% observed. On 2026-09-01 the two top bands were
five to nine points off; with 65 and 52 points in them now, both are within one.
A gap in a thin band is the kind a few dozen more fixtures can close, and it
should be read that way.

## By division

Held-out 2025–2026, against the prior for the same fixtures.

| division | n | poisson | prior |
|---|---|---|---|
| 1部 | 234 | 0.8164 | 1.0189 |
| 2部 | 170 | 0.9358 | 1.0466 |
| 3部 | 163 | 0.7412 | 0.9947 |
| チャレンジリーグ | 30 | 0.6424 | 0.9641 |

The second division is the hardest division to forecast in the league, and by
some distance — the model recovers less than half as much over the prior there as
it does in the third. That is consistent with the conversion-rate anomaly in
[FINDINGS.en.md](../FINDINGS.en.md), which is also a second-division story and also
unexplained.

## Forecasts on the record

Each forecast is kept under the date it was made and never regenerated — a
forecast that is quietly refreshed is not a forecast. When new results arrive,
the previous forecast is scored with the model exactly as it stood, and a new,
separately dated one is added below it.

### 2026-09-01

Made **2026-09-01** from results up to 2026-07-12, with the season's remaining
fixtures resuming on 2026-09-05.

2026 first division, 54 fixtures to play, 10,000 simulated seasons:

| club | played | points | projected | title | top 3 | last |
|---|---|---|---|---|---|---|
| 東京経済大学 | 13 | 33 | 54.7 | 75.8% | 100.0% | 0.0% |
| 帝京大学 | 13 | 30 | 50.7 | 13.3% | 99.7% | 0.0% |
| 桜美林大学 | 13 | 31 | 49.8 | 10.9% | 99.5% | 0.0% |
| 学習院大学 | 13 | 22 | 37.4 | 0.0% | 0.6% | 0.0% |
| 大東文化大学 | 13 | 21 | 35.4 | 0.0% | 0.3% | 0.0% |
| 朝鮮大学校 | 13 | 20 | 27.3 | 0.0% | 0.0% | 0.0% |
| 横浜国立大学 | 13 | 16 | 26.7 | 0.0% | 0.0% | 0.0% |
| 武蔵大学 | 13 | 15 | 26.3 | 0.0% | 0.0% | 0.0% |
| 日本大学文理学部 | 13 | 12 | 22.9 | 0.0% | 0.0% | 0.0% |
| 上智大学 | 13 | 8 | 17.5 | 0.0% | 0.0% | 1.2% |
| 玉川大学 | 13 | 8 | 17.1 | 0.0% | 0.0% | 1.4% |
| 神奈川工科大学 | 13 | 3 | 7.0 | 0.0% | 0.0% | 97.4% |

Note the third row. 桜美林大学 are second on points and third on projection,
0.9 points behind a club they are one point ahead of, because the model rates
帝京大学 higher than the table does on the same number of games played. It is a
small disagreement, but disagreeing with the standings is the only reason to
build one of these.

The *last* column alone was corrected on 2026-09-28. `forecast` had been printing
the chance of each club's own worst simulated finish rather than of finishing
twelfth, so a club that never fell below fourth had its chance of fourth place
printed as its chance of finishing last. The simulation itself is unchanged. Five clubs move, all to
0.0% — 東京経済大学, 帝京大学, 朝鮮大学校, 横浜国立大学 and 武蔵大学 — and the
column now sums to 100%.

### How the 2026-09-01 forecast did

Seventy-two league fixtures were played between 5 and 27 September. They are
scored here by the model as it stood on 2026-09-01, not refitted. Only the first
division's table was published, but the same model put probabilities on every
fixture, so the second and third divisions can be scored on the same terms.

| division | n | poisson | prior | accuracy |
|---|---|---|---|---|
| 1部 | 24 | 0.7351 | 0.9456 | 79.2% |
| 2部 | 20 | 0.8168 | 1.0109 | 60.0% |
| 3部 | 28 | 0.9558 | 1.0356 | 64.3% |
| all | 72 | 0.8436 | 0.9987 | 68.1% |

Better than the prior in all three. Seventy-two fixtures is a small sample,
though, and next to the 597 held-out fixtures above this is an anecdote rather
than evidence.

In the first division every club played four of those fixtures, so the points
it was expected to take from them can be set against the points it did take.

| club | points on 09-01 | expected from 4 | taken from 4 | difference |
|---|---|---|---|---|
| 東京経済大学 | 33 | 10.6 | 9 | −1.6 |
| 帝京大学 | 30 | 10.1 | 9 | −1.1 |
| 桜美林大学 | 31 | 9.4 | 10 | +0.6 |
| 学習院大学 | 22 | 5.9 | 9 | +3.1 |
| 大東文化大学 | 21 | 5.8 | 9 | +3.2 |
| 朝鮮大学校 | 20 | 3.0 | 4 | +1.0 |
| 横浜国立大学 | 16 | 3.6 | 3 | −0.6 |
| 武蔵大学 | 15 | 4.1 | 4 | −0.1 |
| 日本大学文理学部 | 12 | 5.7 | 4 | −1.7 |
| 上智大学 | 8 | 3.1 | 0 | −3.1 |
| 玉川大学 | 8 | 5.8 | 6 | +0.2 |
| 神奈川工科大学 | 3 | 1.6 | 3 | +1.4 |

大東文化大学 (+3.2) and 学習院大学 (+3.1) beat their expectation by the most;
上智大学 (−3.1) fell furthest short, without a point from four games. The two clubs
the 2026-09-01 forecast had in the opposite order to the table went the table's
way: 桜美林大学 took 0.6 more than expected and 帝京大学 1.1 fewer, so the gap
between them widened from one point to two.

### 2026-09-28

Made **2026-09-28** from results up to 2026-09-27. The next fixtures are on
2026-10-03.

2026 first division, 30 fixtures to play (11 of them not yet scheduled), 10,000
simulated seasons:

| club | played | points | projected | title | top 3 | last |
|---|---|---|---|---|---|---|
| 東京経済大学 | 17 | 42 | 52.8 | 67.2% | 100.0% | 0.0% |
| 桜美林大学 | 17 | 41 | 50.3 | 17.8% | 99.8% | 0.0% |
| 帝京大学 | 17 | 39 | 50.1 | 15.0% | 99.8% | 0.0% |
| 学習院大学 | 17 | 31 | 40.3 | 0.0% | 0.4% | 0.0% |
| 大東文化大学 | 17 | 30 | 39.8 | 0.0% | 0.1% | 0.0% |
| 朝鮮大学校 | 17 | 24 | 28.7 | 0.0% | 0.0% | 0.0% |
| 武蔵大学 | 17 | 19 | 26.6 | 0.0% | 0.0% | 0.0% |
| 横浜国立大学 | 17 | 19 | 25.6 | 0.0% | 0.0% | 0.0% |
| 日本大学文理学部 | 17 | 16 | 20.8 | 0.0% | 0.0% | 0.0% |
| 玉川大学 | 17 | 14 | 17.3 | 0.0% | 0.0% | 0.1% |
| 上智大学 | 17 | 8 | 13.3 | 0.0% | 0.0% | 12.8% |
| 神奈川工科大学 | 17 | 6 | 8.9 | 0.0% | 0.0% | 87.1% |

東京経済大学's title chance falls from 75.8% to 67.2%: they took 1.6 points fewer
than expected and their lead is down from two points to one. The three leaders
still have to play one another three times, and two of those three fixtures —
all but 桜美林大学 against 東京経済大学 on 18 October — have no date yet.

The disagreement noted in the 2026-09-01 forecast has gone: 桜美林大学 now sit
above 帝京大学 on projection as well as on points, though only by 0.2.

At the bottom, 上智大学's chance of finishing last rises from 1.2% to 12.8%, as
the gap to 神奈川工科大学 closes from five points to two.

### Reading these tables

Only the outcome of each remaining fixture is simulated, not the scoreline, so
clubs level on points are separated by the goal difference they have already.
Good enough to rank a table; not good enough to quote a goal difference from.

## What this does not do

- **No expected goals.** The federation records shot *counts*, not shot locations,
  so there is no chance quality here and nothing in this document should be read
  as xG.
- **No squad information.** Injuries, suspensions and selection are not in the
  model, though the data holds enough to try.
- **No player-level forecast, and there will not be one.** Predicting individual
  amateur students is profiling; [DATA_POLICY.en.md](DATA_POLICY.en.md) applies here as
  it does everywhere else in this repository. Every number above is a team-level
  aggregate.
- **Fixtures that are not scheduled yet** keep the season's provisional date until
  the federation sets one — 73 of the 128 outstanding fixtures in August 2026,
  and 12 of the 54 league fixtures left in 2026 on 2026-09-28 — and are listed as
  `TBC` rather than pretended into the past.
