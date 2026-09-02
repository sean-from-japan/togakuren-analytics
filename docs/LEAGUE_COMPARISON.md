# Comparing leagues

*[日本語版](LEAGUE_COMPARISON.ja.md)*

Everything else here measures one federation. This measures it against others,
because a number from a single league says nothing until something else has been
measured the same way.

```bash
togakuren compare
togakuren compare --reference docs/reference-leagues.json
```

## The two quantities

**Talent spread.** [Noll and Scully's
ratio](https://en.wikipedia.org/wiki/Competitive_balance) divides the observed
spread of win ratios by the spread a league of identical clubs would show over a
season of that length. It is the standard measure, and it gives the wrong answer
here. A university season is 13 to 21 fixtures per club against 34 to 46 in the
professional leagues, so the larger denominator divides a genuinely wide spread
back down: the Tokyo first division reads 1.88, which is ordinary.

Observed variance is talent plus the noise a season of that length leaves
behind, so subtracting the noise recovers what the clubs actually are:

```
sd_talent = sqrt(sd_observed² − sd_ideal²)
```

**This decomposition is not new.** It is Tango's and Mauboussin's, and James
Grayson and Martin Eastwood have both applied it to the Premier League. Nothing
in `compare.py` is a novel method. What is done here is applying it, and the
measure below, to leagues that the published comparisons leave out.

**Predictability.** How far the [forecasting model](PREDICTION.md) gets below the
class prior, in nats, on the two seasons its half-life was *not* chosen on. Same
estimator for every league, imported rather than re-implemented.

## What this repository ships

`compare` measures each division of this federation as a league in its own right.
Divisions are never pooled: a pyramid measured as one thing reports the gap
between its tiers, not the balance inside any of its leagues. Pooling them is
what produced the first wrong answer this document records.

| division | clubs | fixtures/club | talent sd | Noll-Scully | draws | goals | gain |
|---|---|---|---|---|---|---|---|
| 1部 | 12 | 21 | 0.175 | 1.88 | 17.6% | 3.06 | +0.212 |
| 2部 | 12 | 18 | 0.172 | 1.78 | 15.0% | 3.47 | +0.055 |
| チャレンジリーグ | 11 | 13 | 0.220 | 1.88 | 11.5% | 4.62 | +0.164 |

3部 has three seasons and 4部 has 28 fixtures; neither is measured rather than
being measured badly.

## The reference set

`docs/reference-leagues.json` holds 22 European professional divisions
(2021/22–2025/26) as eight numbers each. **It is a set of derived statistics
about leagues, not a copy of anybody's fixtures** — the same distinction
[DATA_POLICY.md](DATA_POLICY.md) draws for players.

It was built from [football-data.co.uk](https://www.football-data.co.uk/), whose
`robots.txt` is `Disallow:` with an empty value, by running exactly the
`compare.measure` in this package over each division. The fetching code is not
in this repository: a second set of third-party scrapers does not belong in a
project whose [source selection](SOURCE_SELECTION.md) is an argument about being
careful with one. Any reference set of `{talent_spread, gain}` rows works with
`--reference`.

Top flights and lower tiers give slopes 1.013 (se 0.505) and 0.438 (se 0.283) —
a difference of t = 0.99, so one line fits both and they are used as a single
band. With n = 11 each that is low power: *cannot be distinguished*, not
*identical*.

## What came out of it

Fitted on the 22 reference leagues alone:

```
gain = −0.0924 + 1.257 × spread     r = +0.857, R² = 0.735, residual sd 0.0223
```

**Predictability is mostly a function of how far apart the clubs are.** Three
quarters of the variance across professional divisions, with no reference to
what kind of football is being played.

**Two retractions, both from widening the sample.** They are here because the
pattern matters more than either result.

*The Tokyo league is not an outlier.* Pooled into one league it sat 2.54
residual standard deviations above the line. Split into its own divisions the
average residual is −0.08 sd. The pooled figure was inflated because the class
prior was taken over a four-tier population while every scored fixture was
inside one tier.

*Student football is not more predictable.* Measured against 53 NCAA conferences
and the rest of the Japanese university pyramid — 関東 1部/2部, 関西 1部, 九州 1部,
from [soccer-db.net](https://soccer-db.net/), which disallows only `/player/` and
`/compare/` — **関東 1部, the top of Japanese university football, lands inside
the professional band**: talent spread 0.086 against a professional 0.054–0.157,
gain +0.044 against a professional mean of +0.040. So do 関東 2部 and 関西 1部.
Across all seven Japanese university leagues the mean residual is +0.65 sd, which
is noise.

**What does replicate: student fixtures resolve more often.** 46 of 60 student
leagues sit below the lowest professional draw rate of 23.9%, in both countries,
and it survives correcting for the NCAA's extra-time rule. But it fades as the
standard rises — 関東 1部 at 21.0% and 3.03 goals is nearly professional in shape,
チャレンジリーグ at 11.5% and 4.62 is not — so it reads as a property of the level
of football rather than of the players being students.

**A negative result: league memory is not shorter for students.** The half-life
justified in [PREDICTION.md](PREDICTION.md) by squads turning over every year is
250 days for the Tokyo divisions and 250 for the professional leagues, and across
23 leagues the chosen half-life ranges 120–4000 days with no relation to talent
spread (r = −0.208 on the log). Decay helps everywhere; there is no evidence it
needs to be shorter here.

## What may be claimed

Not "student football is X": the population spans nearly the whole range of the
map, and its top end is indistinguishable from professional football. What is
defensible is the machinery and the placement — that university leagues run from
関東 1部, which reads professional, to チャレンジリーグ, which does not.

The mechanism behind the match-shape result is not shown. Residual against goals
per fixture is +0.219 and against draw rate −0.289 over 78 leagues, so it is a
hypothesis the numbers are consistent with, not one they demonstrate.

Home advantage is **excluded from every comparison here**. football-data names
the host for every fixture, this federation's API never does and it is inferred
from venue usage for 59% of them — biased towards clubs with their own ground —
and the third source does not record it at all. Three different measurements
should not be put in one column.
