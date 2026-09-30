# Changelog

Dates are the day the work landed on `main`.

## Unreleased

### Added

- **The dashboard now answers a club's own question: what is left, and what is
  it worth.** Selecting a club shows every league fixture it has from its own
  side — results with the score, then the fixtures left in date order, the
  unscheduled ones marked TBC — and clicking an opponent switches to them.
  `dashboard --forecast` adds, per fixture left, the chance of winning, drawing
  and losing and the points the club can expect from it; a chart of points
  taken, with the expected path and the 80% range through the rest of the
  season; the chance of every finishing position; and a projected final table. The model, cut-off and
  seed are the `forecast` command's, so the page and the command agree to the
  digit. Every number is team-level, so `--privacy aggregate --public` allows it.
- `predict.points_path` gives one club's points distribution after each of its
  remaining fixtures exactly, by convolution, where the season simulation
  samples. The chart's range comes from it.
- **A second forecast on the record, and a score for the first.**
  [docs/PREDICTION.en.md](docs/PREDICTION.en.md) keeps the 2026-09-01 table and
  adds one made on 2026-09-28 from results up to 2026-09-27. Between the two, the
  72 league fixtures played from 5 to 27 September are scored by the 2026-09-01
  model as it stood: log loss 0.8436 against the prior's 0.9987, better in all
  three divisions. The first division also gets each club's expected against
  actual points over the four games it played in that time.
- `docs/SITE_ARCHITECTURE.{en,ja}.md` documents the official site's WordPress,
  Vue and Cockpit split, every request made by the match page, the data crossing
  that boundary, and a security assessment with architecture and sequence
  diagrams. The review found that an unfiltered request made with the public
  browser token returned one unpublished series; no identifier or content from
  it is recorded.
- **`togakuren intake` — what the squad list is worth before a ball is kicked.**
  The registration list names every player, their academic year, and the high
  school or club youth side they came from, and it is public before the season
  starts. Scored leave-one-season-out against the only baseline that matters,
  last season's final table: the squad list is worth **+12.8%** against the
  division average over 191 club-seasons, where the table alone scores
  **−0.2%**. New modules `togakuren/origins.py` (parsing the free-text origin
  column) and `togakuren/intake.py` (features and scoring), plus
  `togakuren/reference-schools.json` — the schools that reached editions 97–104
  of the All-Japan High School Championship, from Japanese Wikipedia under
  CC BY-SA 4.0.
- `intake --validate` also splits the correlation by what the club had just
  done, which is where the second result came from: after **relegation**, a
  club's own last table predicts the coming season at r = +0.017, and its squad
  list at +0.568.
- `privacy-check` now measures the school column too, because the model above is
  built on it. It takes the 2026 first division from 105 unique rows of 189 to
  **184**, which is why no per-player output carries it in any privacy mode.
  [docs/DATA_POLICY.en.md](docs/DATA_POLICY.en.md) has the table.
- `--lang en|ja` on the two HTML pages, `trends` and `dashboard`. Every string
  the charts draw now arrives in the page payload rather than being written into
  the drawing code, so the axes, legends, tooltips and captions follow the
  language.

### Fixed

- **`forecast` printed the wrong chance of finishing last.** The *last* column
  took each club's own worst simulated finish instead of twelfth place, so a
  club that never fell below fourth had its chance of fourth place printed as
  its chance of finishing last, and the column summed to more than 100%. The simulation was right; only
  the column was wrong. The 2026-09-01 table is corrected in place, with a note:
  five clubs move to 0.0%, and the three that could finish last are unchanged.
- **"Without time decay" in PREDICTION had been measured with a ten-year
  half-life.** 0.9137 reproduces at 3,650 days; with no decay at all the same
  fixtures give 0.9272. On the current data the row reads 0.9227, +0.102. The
  conclusion — decay is worth more than everything else together — gets stronger.
- **The Elo carry-over paragraph named the wrong setting.** On 2025–2026 the
  better score was keeping all of last season's rating, not discarding it. Keep
  all, the worst choice on 2022–24, was the best on 2025–26 (0.8606 against
  0.8672 for half and 0.8709 for none), so the "no consistent answer" conclusion
  stands, and more starkly.
- `Client.series()` now always requests `published:true` and projects only the
  six competition fields ingestion needs. The federation's visible page already
  applies the publication filter, but this client did not, despite promising to
  request only already-published content.
- **The documents used statistical notation without ever defining it.** `r`,
  `RMSE`, `n`, `R²`, `se`, `t`, `MSE`, Brier and "vs the division average" all
  carried headline claims while being introduced nowhere, so a reader outside
  the field could not tell whether +0.017 was small or large. FINDINGS now has a
  `Notation` section before the first result, the section 2 correlation columns
  say they are `r`, and LEAGUE_COMPARISON, PREDICTION, RATINGS and
  LEAGUE_STRUCTURE gloss their own metrics at first use. No number changed.

- **The Japanese documents mixed sentence registers.** Nine files carried 126
  sentences that dropped out of です・ます into plain だ・である mid-document,
  almost all of them either the closing sentence of a section or a bold
  run-in — the places where plain form sounds more decisive. Mixed registers
  read as content-farm Japanese, which is the wrong impression for a document
  whose subject is measurement. Every `*.ja.md` is now です・ます throughout,
  and so are the Japanese label dictionaries the generated documents and the
  HTML pages are built from. 体言止め is untouched: used consistently for
  captions and labels it is correct, and only plain verbs and adjectives were
  changed.
- `tests/test_docs.py::JapaneseRegister` enforces it, over both the documents
  and the label dictionaries in `markdown.py`, `trends.py` and `dashboard.py`.
  Fixing a generated document by hand would otherwise be undone by the next
  regeneration.

- **`docs/figures/fig-promotion.png` was unreadable.** It had been shot on a
  light background while the page's colours were the dark ones, so both axis
  captions were pale grey on white. Re-shot on the dark palette like the other
  five, and the two captions are drawn at full contrast rather than at the tick
  labels' opacity. [docs/FIGURES.en.md](docs/FIGURES.en.md) now says how to
  shoot a figure without repeating this.
- **The club history table was blank on every aggregate dashboard**, including
  the screenshot in the README. Aggregate mode omits the minutes grid and the
  squad table, so two of `select()`'s draw calls had no element to write into;
  the first threw, and every later call in the same function never ran. Both
  draw functions now tolerate a missing host.
- The conversion chart drew the third division and the Challenge League as the
  same colour. Lines are coloured by division rather than by the level the
  division started on, and those two both began at level three.
- The club trajectory chart labelled its y axis with division names while
  positioning points by level, so the 2022 Challenge League appeared on the
  "3部" row. The axis is labelled by level, with the mismatch explained under
  the chart.

### Changed

- **The 2026 season is loaded through 2026-09-27** — first division 102/132,
  second 80/90, third 91/105 — and every number in PREDICTION is re-scored on it.
  Held out, 2025–2026 goes from 525 to 597 fixtures: Poisson 0.8211 against Elo
  0.8672 and the prior 1.0174. The tuning window's Elo moves from 0.8649 to
  0.8650 without a 2022–24 result changing: September's fixtures took
  武蔵野大学松芝園グラウンド past the three-fixture threshold, and home grounds
  are inferred from every fixture loaded, earlier ones included.
- The three 2026 season documents, `docs/seasons/README.md` and SEASON_TRENDS
  are regenerated. The finished seasons' documents change only in the 2026 row
  of each club's division history.
- **FINDINGS is reordered and largely rewritten.** The promotion section led on
  a result nobody needed telling — a promoted club takes fewer points — so it
  now opens with what the move does to predictability instead, and the size of
  the drop is kept as context. The preseason model is the new first section, and
  a third section records the two things that were tried to improve it and did
  not: a second pedigree source that turned out to measure the same thing
  (r = 0.866, +0.2 points), and an endogenous school rating that made the model
  worse.
- **The committed figures are now two sets, `docs/figures/en/` and
  `docs/figures/ja/`.** The English documents had been illustrated with
  Japanese-labelled charts. Club names stay as the federation writes them in
  both sets. `docs/example-dashboard.png` becomes
  `docs/example-dashboard.en.png` and `.ja.png`.
- `fig-trajectory.png` now opens on a club that actually moves between levels,
  which is what the chart is for.

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
