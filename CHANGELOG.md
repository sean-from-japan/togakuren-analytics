# Changelog

Dates are the day the work landed on `main`.

## Unreleased

### Changed

- Every bilingual Markdown document now names its language explicitly with
  `.en.md` or `.ja.md`. The root `README.md` is a short language-neutral index
  linking to `README.en.md` and `README.ja.md`.
- Generated Markdown uses one central filename function, so English and
  Japanese defaults cannot overwrite each other or leave one language
  unlabeled. The regression tests enforce the pairing rule.
- The Japanese documentation and dashboard copy were edited as Japanese prose,
  including football terminology and mixed-language UI labels. A small
  regression check blocks the literal translations corrected in this pass.

## 0.3.0 — 2026-09-02

### Fixed

- **Division levels are now read from the divisions that actually ran each
  season, not from a fixed name-to-level map.** The competition was rebuilt
  three times between 2021 and 2026 and the Challenge League's level is not in
  its name: it was the third level from 2022 and the fourth from 2025, after a
  third division was inserted above it. The old map put it at 5 in every year,
  which reversed the direction of **15 of 72 division changes (21%)** — seven
  promotions filed as relegations, six lateral moves filed as relegations, and
  two lateral moves filed as promotions. `analysis.season_ladder` replaces
  `analysis.TIERS`. See [docs/LEAGUE_STRUCTURE.en.md](docs/LEAGUE_STRUCTURE.en.md).
- `division_moves` now carries `moved`, false for the five Challenge League
  clubs that lost a level in the 2025 reorganisation without changing division
  or playing a match. A reorganisation is not a relegation, and `trends` and
  `profiles` leave them out of both the averages and the chart.
- `grade_trend` filters on the division's name rather than its level, which is
  what its callers were labelling their tables with all along. Filtering on a
  level put the 2022–24 Challenge League and the 2025–26 third division into one
  table and dropped the Challenge League heading entirely.
- `trends --format md --lang ja` silently overwrote the English document.
  It now appends the Japanese language suffix, as
  `profiles` already did.

### Changed

- **The promotion and relegation figures move, and one claim is withdrawn.**
  Promotion: 27 cases at −1.04 becomes 32 at −0.97, 29 of 32 worse, and it holds
  inside each reorganisation separately. Relegation: 30 cases at +0.53 becomes
  17 at **+1.24**, 1 of 17 worse. The asymmetry FINDINGS reported — promotion
  costs a full point, relegation returns half, three in ten keep falling — was
  an artefact of the mislabelled cases and is retracted.
- `docs/figures/fig-promotion.png` re-shot: the correction recolours fifteen
  points and removes five, so the old picture contradicted the corrected text.
  915 × 640, replacing 992 × 539.
- **The README became Japanese-first**, with the English text moved to
  `README.en.md`. This was later replaced by the language-neutral index noted
  under Unreleased, while the full Japanese and English documents remain.
- FINDINGS drops the section on one club crossing three tiers in five years.
  The rise is a recruitment decision by the club, not something measured here,
  so it does not belong among the results.
- **The dashboard's fingerprint radars are readable on their own.** The small
  charts carried no axis labels at all, so a shape could not be read without
  guessing which vertex was which; each vertex now shows the index number, and
  the list under the grid is numbered to match. Every radar also draws the
  league mean as a dashed outline, so a club reads as a deviation from the
  field. Because each axis is min-max scaled inside the series, that mean is
  not 50, and the list prints it per index.
- `docs/figures/fig-fingerprints.png` re-shot for the numbered vertices and the
  mean outline, 2026 1部リーグ as before. 1104 × 397, replacing 1104 × 386. The
  season documents and FINDINGS say what the numbers and the dashed outline are.
- `docs/example-dashboard.png` re-shot for the same reason: the README's
  screenshot still showed unnumbered radars. 1160 × 1290, unchanged. It is a
  screenshot that no command regenerates, and it was missed because FIGURES
  covered only `docs/figures/`; it is now in that table.

### Added

- `docs/LEAGUE_STRUCTURE.en.md` and `.ja.md`: what ran in each season, what each
  reorganisation did to the club pool, how large the 2023 discontinuity is
  (a first-division club that stood still gained 0.83 points a game across it,
  five times the movement at any other boundary), and what the correction did
  to the published figures.

## 0.2.0 — 2026-09-01

### Added

- `forecast` and `backtest`: a time-decayed Poisson with a Dixon-Coles low-score
  correction, fitted by closed-form coordinate ascent. Settings were fixed on
  2022–2024 and not touched again; on 2025–2026 league fixtures (n = 525) the
  log loss runs 1.0200 (class prior) → 0.8753 (Elo) → 0.8192, and accuracy 44.6%
  → 65.7%. See [docs/PREDICTION.en.md](docs/PREDICTION.en.md).
- `ratings`: adjusted plus-minus over segments cut at kick-off, every
  substitution and every dismissal, solved by conjugate gradient. See
  [docs/RATINGS.en.md](docs/RATINGS.en.md).
- `ratings --tune`: chooses the two ridge penalties by cross-validation *inside*
  each training fold.
- `ratings --forward`: the forward split — fit the first 60% of each season,
  predict the rest of it — now in the package rather than quoted from a
  prototype.
- `compare` and `togakuren/compare.py`: each division measured as a league in its
  own right — Noll-Scully, the noise-corrected talent spread that Noll-Scully
  gets wrong for a short season, match shape, and predictability against a
  reference set. `docs/reference-leagues.json` ships 22 European professional
  divisions as derived statistics so `--reference` works out of the box. See
  [docs/LEAGUE_COMPARISON.en.md](docs/LEAGUE_COMPARISON.en.md), which also records the
  two headline results that widening the sample destroyed.
- `docs/SOURCE_SELECTION.en.md`: why this league and not the tier above, in terms
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
- `docs/FIGURES.en.md`: which chart each committed PNG is a picture of, how to remake
  one, and why the step is not automated. The six figures were the only thing
  here that no command could reproduce and nothing said where they came from.

### Fixed

- **Commands now close the database they open.** Every one of the twelve opened a
  connection and none of them closed it. Harmless on macOS and Linux; on Windows
  an open SQLite handle keeps the file locked, so a caller could not remove the
  directory around it. Found by running the new command tests on Windows CI.
- **`forecast --runs 0` divided by zero, and `--runs -5` was worse**: the
  simulation loop simply did not run and every club came back with an expected
  zero points, which reads as an answer rather than as a mistake. Counts that
  cannot sensibly be zero are now validated by argparse.
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
- **The forward-split figure was replaced, not reconciled.** RATINGS.en.md quoted
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
