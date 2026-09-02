# Changelog

Dates are the day the work landed on `main`.

## 0.2.0 — 2026-09-01

### Added

- `forecast` and `backtest`: a time-decayed Poisson with a Dixon-Coles low-score
  correction, fitted by closed-form coordinate ascent. Settings were fixed on
  2022–2024 and not touched again; on 2025–2026 league fixtures (n = 525) the
  log loss runs 1.0200 (class prior) → 0.8753 (Elo) → 0.8192, and accuracy 44.6%
  → 65.7%. See [docs/PREDICTION.md](docs/PREDICTION.md).
- `ratings`: adjusted plus-minus over segments cut at kick-off, every
  substitution and every dismissal, solved by conjugate gradient. See
  [docs/RATINGS.md](docs/RATINGS.md).
- `ratings --tune`: chooses the two ridge penalties by cross-validation *inside*
  each training fold.
- `ratings --forward`: the forward split — fit the first 60% of each season,
  predict the rest of it — now in the package rather than quoted from a
  prototype.
- `docs/SOURCE_SELECTION.md`: why this league and not the tier above, in terms
  of what each federation publishes and what its site says about being read by a
  program.
- Document link checking in the test suite: anchors, relative links, and that
  every `*.ja.md` has an English counterpart.
- 52 tests for the API client and the command layer, the two least covered
  modules — 17.5% of statements were unreached before, 5.7% after. The client is
  exercised against a stubbed transport: token discovery, the retry rule (4xx
  once, 5xx three times), the request throttle, and the on-disk cache. Every CLI
  command now runs end to end through `main`.
- A fixture for a season with a match still to play, so `forecast` is covered by
  something other than its refusal to run.
- `docs/FIGURES.md`: which chart each committed PNG is a picture of, how to remake
  one, and why the step is not automated. The six figures were the only thing
  here that no command could reproduce and nothing said where they came from.

### Fixed

- **Commands now close the database they open.** Every one of the twelve opened a
  connection and none of them closed it. Harmless on macOS and Linux; on Windows
  an open SQLite handle keeps the file locked, so a caller could not remove the
  directory around it. Found by running the new command tests on Windows CI.
- `ratings --forward` raised a bare `ValueError` at the caller when a sample was
  too small to cut 60/40 inside a season. It now exits with a message. Found by
  the new command tests.
- `__version__` said 0.1.0 while `pyproject.toml` said 0.2.0, and the client's
  user agent hard-coded 0.1. All three now come from one place, and a test keeps
  them together.

### Changed

- **Conversion rate is no longer overstated.** It divided every goal a club
  scored by the shots recorded for it, but 776 of 4,368 game-teams have no shot
  rows at all. Goals and shots now come from the same fixtures, and
  `shot_coverage` reports how much of a season the rate is taken over. 2部 2023
  moves 0.189 → 0.182 and チャレンジ 2022 moves 0.233 → 0.216; every 1部 season
  is unchanged.
- **The ratings figure is now honest about where its penalties came from.** They
  were module constants chosen by cross-validation over every fixture the
  reported score was then computed on. Chosen inside each fold instead, the gain
  from knowing the players is **+3.73%** rather than +4.07%.
- **The forward-split figure was replaced, not reconciled.** RATINGS.md quoted
  +5.44% from a prototype that predates the package. It does not reproduce — the
  split divides 741/494 rather than 735/500 and the errors do not come back — so
  it now reports what the shipped code prints, +4.06%.
- README leads with the results and the two limits of the source, rather than
  with prose. FINDINGS opens with a summary ordered by how little the result was
  already obvious, which puts the promotion figure last.
- `validate()` returns `Validation(scores, penalties)` so the chosen penalties
  can be reported rather than implied.
- The takedown offer covers the clubs whose results appear here, not only the
  federation.
- The README states the author's past connection to a club in this league.

## 0.1.0 — 2026-08-29

First public version. Collection, the database, team and season analysis, the
dashboard, the 40 generated season documents, the data policy and
`privacy-check`.
