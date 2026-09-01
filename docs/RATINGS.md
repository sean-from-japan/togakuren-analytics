# Adjusted plus-minus ratings

How much does knowing *who* is on the pitch tell you, beyond knowing which two
clubs are playing? For this league the answer is: a little, and it is measurable.

```
togakuren ratings --validate     # the table below
togakuren ratings                # the players, locally
```

## The method, and why this source suits it

Sæbø and Hvattum's plus–minus rating cuts a match into segments at kick-off, at
every substitution and at every dismissal, so the twenty-two players on the pitch
are fixed inside a segment. The response is the goal difference scored inside the
segment. Every player present enters the regression as +1 for their own side and
−1 for the other, scaled by the segment's share of a full match, and a ridge
penalty keeps a player who appeared for twenty minutes from being handed twenty
minutes' worth of noise.

Kick-off, substitutions with a minute, dismissals with a minute, goals with a
minute. That is the whole input, and it is exactly what this federation records —
which is unusual, because it does not require event data, tracking data or
anything a broadcaster would sell. `appearances.on_minute` and `off_minute`,
which exist so that minutes played can be reconstructed at all, already carry it.

Over 2022–2026 league fixtures:

| | |
|---|---|
| fixtures with a complete eleven on both sides | 1,569 |
| fixtures used, after reconciliation (below) | **1,235** |
| segments | **8,087**, mean length 13.7 minutes |
| players | 3,503, of whom 2,242 clear 270 minutes |
| segments where the venue identifies a host | 60% |

## Goals that do not add up

The timed goal events reconcile with the recorded score in **1,235 of 1,569
fixtures, 79%**. Nearly every gap is a single goal, and the cause is that the
federation stores unattributed and own goals as a count on the match record
rather than as an event with a minute.

A segment model cannot place a goal it has no minute for. The fixtures that do
not reconcile are therefore left out rather than quietly mis-scored, and the
command says how many that was. `--validate` on the unreconciled set is available
through the library (`segments(..., reconcile=False)`) if you want to see the
difference for yourself.

## What it is worth

Grouped five-fold cross-validation — whole fixtures are held out, so no segment
of a test match is ever in training. The error is on the goal difference of the
whole match, formed by summing the model's segment predictions.

| model | MSE | vs zero |
|---|---|---|
| zero | 6.7676 | — |
| clubs | 4.4667 | −34.0% |
| players, no club terms | 5.2921 | −21.8% |
| **clubs + players** | **4.2851** | **−36.7%** |

Knowing the players and not just the clubs: **+4.07%**.

A stricter check, because cross-validation of this kind measures how well the
ratings *describe* a season rather than how well they carry forward: fit on the
first 60% of each season's fixtures and predict the rest of that same season.

| model | MSE | vs zero |
|---|---|---|
| zero | 6.3180 | — |
| clubs | 4.3427 | −31.3% |
| **clubs + players** | **4.1062** | **−35.0%** |

Knowing the players and not just the clubs: **+5.44%**, over 735 training and 500
test fixtures. The forward split is the harder test and it comes out slightly
better, which is the right way round.

Home advantage falls out of the same fit at **+0.26 goals per 90**. It is
estimated from the venue, since the API records a venue and never a host — see
[PREDICTION.md](PREDICTION.md) for how that inference works and how often it
succeeds.

## Two things that will reverse the result if you get them wrong

**Club terms and player terms need separate penalties.** Fifty-odd clubs need
almost no shrinkage; two thousand players need a great deal. Put them under one
penalty tuned for the players and the club effects are over-shrunk, at which
point the joint model scores *worse* than clubs alone and the honest conclusion
looks like "player identity adds nothing". `Design.penalties` takes the two
separately for this reason.

**Do not form the normal equations.** With a few thousand columns the matrix is
millions of entries, and building it is the slow part rather than solving it.
Each design row has about twenty-three non-zeros, so conjugate gradient over the
sparse rows reaches the same answer — the tests check it against a direct
elimination on a small problem — in a few seconds of pure Python, and this
package keeps its standard-library-only rule.

## What is not here

The ratings themselves. They are per player, and the people in this dataset are
amateur students, so `ratings` prints them and never writes them to a file, the
same rule every other player-level output follows. The validation tables above are
aggregates and carry no individual, which is why they are the part that is
published. See [DATA_POLICY.md](DATA_POLICY.md).

Two limits are worth repeating from the README. Penalties cannot be separated
from open play in this source, so a designated taker's goals sit in these numbers
like anyone else's. And identification rests on substitutions and dismissals — a
side that never changes its eleven gives the model nothing to separate its
players with, and the ridge penalty will pull all eleven towards the same value.
