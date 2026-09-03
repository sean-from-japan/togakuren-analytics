# Forecasting

Every other document here describes what happened. This one makes claims about
what has not happened yet, so it is written to be checked rather than believed:
each model is scored against the class prior, on fixtures it has not seen, and
the settings were chosen on 2022–2024 and then left alone so that the 2025–2026
numbers below are out of sample.

```bash
togakuren backtest --league-only --until 2024   # the tuning window below
togakuren backtest --league-only --start 2025   # the held-out block below
togakuren forecast --series "2026 1部"          # the fixtures still to play
```

One thing is not accounted for below. The league merged with Kanagawa's in 2023
and the club pool changed with it, so the tuning window straddles a change of
competition ([LEAGUE_STRUCTURE.md](LEAGUE_STRUCTURE.md)). The 180-day half-life
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

## Results

League fixtures only. Settings were chosen on the first block and not revisited.

**Tuning window, 2022–2024 (n = 1,090)**

| model | log loss | Brier | accuracy |
|---|---|---|---|
| prior | 1.0090 | 0.6150 | 42.0% |
| elo | 0.8649 | 0.5022 | 62.9% |
| poisson | 0.8311 | 0.4779 | 66.3% |

**Held out, 2025–2026 (n = 525)**

| model | log loss | Brier | accuracy |
|---|---|---|---|
| prior | 1.0200 | 0.6204 | 44.6% |
| elo | 0.8753 | 0.5099 | 61.3% |
| **poisson** | **0.8192** | **0.4750** | **65.7%** |

The prior is high here for a football league because draws are rare: 15.5% of the
2,184 finished fixtures, against roughly a quarter in professional football. Two
university sides are less likely to be evenly matched than two professional ones,
which is the same reason the model gets as far as it does.

## What actually mattered

Each row removes one thing from the full model. Held-out 2025–2026 league fixtures.

| variant | log loss | change |
|---|---|---|
| poisson | 0.8192 | — |
| without the Dixon-Coles term | 0.8211 | +0.002 |
| without the home term | 0.8268 | +0.008 |
| **without time decay** | **0.9137** | **+0.095** |

**Time decay is the whole game.** A model that weights a fixture from four years
ago the same as one from last month is worse than Elo. Weighting a fixture by a
180-day half-life is worth more than every other refinement here put together —
which is what a competition whose squads are rebuilt every April should look
like.

**How much of last season carries over did not replicate.** Elo has a parameter
for how far ratings are pulled back to the mean between seasons. On 2022–2024,
keeping half of a club's rating clearly beat both keeping all of it (0.8649
against 0.8917) and discarding it entirely (0.8681). On 2025–2026 the ordering
reversed and discarding it won (0.8676 against 0.8753). Two windows, two answers,
so there is no answer here — only the continuous decay above, which does hold up
across both.

## Home advantage

The API records a venue for each fixture and never a host, so home is inferred:
a ground used at least three times, with the same club involved in at least 75%
of those fixtures, is that club's. That identifies a host for **1,015 of the
2,184 finished fixtures**; the rest are treated as neutral, which many of them
genuinely are.

Where a host is identifiable, it wins 45.5%, draws 18.9% and loses 35.6% —
**1.555 points per game against 1.256**. The fitted model puts the effect at
+13.5% on the scoring rate.

As a forecasting term it is worth less than that sounds: it applies to under half
the fixtures, it improved the held-out block by 0.008 nats, and on the tuning
block it was very slightly *negative*. It is kept because it is measurable in the
results and mechanically plausible, not because the forecast needs it.

## Calibration

Held-out 2025–2026 league fixtures, every outcome of every fixture as one point.

| predicted | n | mean predicted | observed |
|---|---|---|---|
| 0–10% | 196 | 4.9% | 4.6% |
| 10–20% | 465 | 16.3% | 15.9% |
| 20–30% | 248 | 23.8% | 23.8% |
| 30–40% | 140 | 35.0% | 28.6% |
| 40–50% | 138 | 44.9% | 49.3% |
| 50–60% | 134 | 54.9% | 57.5% |
| 60–70% | 90 | 65.2% | 64.4% |
| 70–80% | 66 | 74.6% | 75.8% |
| 80–90% | 49 | 85.0% | 93.9% |
| 90–100% | 49 | 95.1% | 89.8% |

Close to the diagonal where the data is thick. The 30–40% band is the one real
miss — those outcomes happened 28.6% of the time — and the two top bands, on 49
points each, are too thin to read anything into.

## By division

Held-out 2025–2026, against the prior for the same fixtures.

| division | n | poisson | prior |
|---|---|---|---|
| 1部 | 210 | 0.8273 | 1.0273 |
| 2部 | 150 | 0.9478 | 1.0513 |
| 3部 | 135 | 0.7031 | 0.9861 |
| チャレンジリーグ | 30 | 0.6425 | 0.9641 |

The second division is the hardest division to forecast in the league, and by
some distance — the model recovers less than half as much over the prior there as
it does in the third. That is consistent with the conversion-rate anomaly in
[FINDINGS.md](../FINDINGS.md), which is also a second-division story and also
unexplained.

## A forecast on the record

Made **2026-09-01** from results up to 2026-07-12, with the season's remaining
fixtures resuming on 2026-09-05. Not regenerated afterwards — a forecast that is
quietly refreshed is not a forecast.

2026 first division, 54 fixtures to play, 10,000 simulated seasons:

| club | played | points | projected | title | top 3 | last |
|---|---|---|---|---|---|---|
| 東京経済大学 | 13 | 33 | 54.7 | 75.8% | 100.0% | 0.1% |
| 帝京大学 | 13 | 30 | 50.7 | 13.3% | 99.7% | 0.3% |
| 桜美林大学 | 13 | 31 | 49.8 | 10.9% | 99.5% | 0.0% |
| 学習院大学 | 13 | 22 | 37.4 | 0.0% | 0.6% | 0.0% |
| 大東文化大学 | 13 | 21 | 35.4 | 0.0% | 0.3% | 0.0% |
| 朝鮮大学校 | 13 | 20 | 27.3 | 0.0% | 0.0% | 0.1% |
| 横浜国立大学 | 13 | 16 | 26.7 | 0.0% | 0.0% | 0.4% |
| 武蔵大学 | 13 | 15 | 26.3 | 0.0% | 0.0% | 0.3% |
| 日本大学文理学部 | 13 | 12 | 22.9 | 0.0% | 0.0% | 0.0% |
| 上智大学 | 13 | 8 | 17.5 | 0.0% | 0.0% | 1.2% |
| 玉川大学 | 13 | 8 | 17.1 | 0.0% | 0.0% | 1.4% |
| 神奈川工科大学 | 13 | 3 | 7.0 | 0.0% | 0.0% | 97.4% |

Note the third row. 桜美林大学 are second on points and third on projection,
0.9 points behind a club they are one point ahead of, because the model rates
帝京大学 higher than the table does on the same number of games played. It is a
small disagreement, but disagreeing with the standings is the only reason to
build one of these.

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
  amateur students is profiling; [DATA_POLICY.md](DATA_POLICY.md) applies here as
  it does everywhere else in this repository. Every number above is a team-level
  aggregate.
- **Fixtures that are not scheduled yet** keep the season's provisional date until
  the federation sets one — 73 of the 128 outstanding fixtures in August 2026 —
  and are listed as `TBC` rather than pretended into the past.
