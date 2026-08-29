# togakuren-analytics

Collect and analyse match records from the Tokyo University Football Association
(東京都大学サッカー連盟), which runs the Tokyo/Kanagawa university leagues.

The federation publishes fixtures, results and a top-scorers list. The records
behind them are far more detailed than the pages let on — per-player shot counts,
the starting eleven, timed substitutions, cards with offence codes — and none of
it is aggregated anywhere. This turns those records into a queryable database and
the rate metrics the site never shows: minutes played, shots per 90, conversion
rate, when a team's shots and substitutions actually arrive.

**No collected data is committed here.** The repository is code, and the people in
this dataset are amateur students — see [docs/DATA_POLICY.md](docs/DATA_POLICY.md).

📊 **[Findings](FINDINGS.md)** ([日本語](FINDINGS.ja.md)) — six things the
federation's own pages do not show, with the charts: what promotion actually
costs a squad, why a single season says nothing about year groups, and how far
league position and shot volume come apart.

![Example dashboard](docs/example-dashboard.png)

*Above: the dashboard in aggregate mode, which omits every per-player view. The
local version adds the squad table and a matchday-by-player minutes grid.*

## Documents

| | |
|---|---|
| [FINDINGS.md](FINDINGS.md) · [ja](FINDINGS.ja.md) | Six results with the charts. Start here. |
| [docs/TEAM_PROFILES.md](docs/TEAM_PROFILES.md) · [ja](docs/TEAM_PROFILES.ja.md) | Every club in the division: numbers, indices, year groups, history. Generated. |
| [docs/PLAYER_ANALYSIS_SAMPLE.md](docs/PLAYER_ANALYSIS_SAMPLE.md) · [ja](docs/PLAYER_ANALYSIS_SAMPLE.ja.md) | What the player-level output looks like, over an **invented** season. Generated. |
| [docs/DATA_POLICY.md](docs/DATA_POLICY.md) · [ja](docs/DATA_POLICY.ja.md) | What may be published, what may not, and the measurements behind the answer. |

The two generated documents come out of the tool in both languages
(`--lang en|ja`), so only prose is ever translated by hand and the numbers
cannot drift between versions. Regenerate them with:

```bash
togakuren profiles --series "2026 1部" --out docs/TEAM_PROFILES.md
togakuren sample --out docs/PLAYER_ANALYSIS_SAMPLE.md
```

## Install

Python 3.9 or newer. No dependencies — standard library only, including the
charts.

```bash
git clone https://github.com/sean-from-japan/togakuren-analytics
cd togakuren-analytics
pip install .          # or run it in place with python3 -m togakuren
```

## Use

```bash
# every season the federation still publishes (~2,300 fixtures, about 40 seconds)
togakuren ingest

# or just one year
togakuren ingest --year 2026

togakuren list                                       # what is loaded
togakuren dashboard --series "2026 1部"              # interactive, team selector
togakuren report --series "2026 1部"                 # flat standalone HTML
togakuren export --series "2026 1部" --out d1.csv    # per-player season rows
togakuren trends                                     # every season at once
togakuren profiles --series "2026 1部"               # the division as Markdown
togakuren sample                                     # player-level output, invented data
togakuren privacy-check --series "2026 1部"          # how identifiable an export is
```

`--series` takes a series id or any set of search terms that narrows to one
series, so `"2026 1部"` is enough.

### What the dashboard shows

Both views are one self-contained file with no external assets — no CDN, no
build step, no server.

**League level**

- **Position × shot volume × goals.** Rank on the x axis, shots per game on the
  y, total goals as circle area. A side that shoots a lot without scoring
  separates visibly from one that converts a handful of chances.
- **Six-axis team fingerprints** — shot volume, finishing, defence, rotation,
  youth and late push, each scaled within the series. Twelve small radars side by
  side make a settled veteran side and a young rotating one different *shapes*,
  not different numbers.
- **Points accumulated by matchday**, all teams at once, the selected one
  highlighted.
- **Goals split by the opponent's half of the table** — feasting on the bottom
  and going quiet against the top looks identical in a goals column.

**Team level**, behind a selector button

- **A matchday × player minutes grid.** The single most useful view for a
  squad: who actually plays, who rotates, who disappears after a certain week. A
  settled side is a solid block; a rotated one is mottled.
- **Minutes and goals by academic year**, plus mean year weighted by minutes.
- **The club's history across divisions**, followed by its federation-wide id, so
  relegation and promotion appear as a change of division on consecutive rows.
- The full squad table with per-90 rates.

**Across seasons** (`togakuren trends`)

One season answers who is good now; several answer the questions that made the
backfill worth doing. Aggregates throughout, so this page is publishable as it
stands.

- **League level over time** — goals, shots and conversion per division, with
  seasons still in progress drawn faintly so they are not mistaken for finished
  ones.
- **Academic year over time**, per division: minutes share as stacked columns
  and scoring rate as a line. Enough seasons to tell a real pattern from one
  cohort being strong.
- **Club trajectories** — tier on an inverted axis, so promotion reads as the
  line going up, sized by points per game.
- **Promotion and relegation as a natural experiment** — the same squad, a year
  later, against different opposition.

The database and the response cache go to a per-user data directory
(`~/Library/Application Support/togakuren-analytics` on macOS,
`$XDG_DATA_HOME` elsewhere), not the working directory. Override with
`$TOGAKUREN_HOME`, `--db` or `--cache`.

## What gets collected

| Table | Contents |
|---|---|
| `series` | one row per competition-season |
| `games` | fixtures: section, kickoff, venue, regulation length |
| `game_teams` | one row per team per fixture: score, points, fair-play points |
| `appearances` | who played, in which role, and **for how many minutes** |
| `squad_members` | academic year, shirt number, position — the year group data |
| `shots` | per player per match, split into halves and extra time |
| `events` | goals and cards with the minute and the offence code |
| `substitutions` | who came off, who came on, when |
| `standings` | the league table the federation computes |
| `players` | names — the only free-text personal data, and droppable |

A full backfill as of August 2026:

| Season | Series | Fixtures | Appearances | Shot rows | Substitutions |
|---|---|---|---|---|---|
| 2026 | 4 | 350 | 6,633 | 8,564 | 1,720 |
| 2025 | 6 | 370 | 10,979 | 14,062 | 2,892 |
| 2024 | 6 | 426 | 12,451 | 15,795 | 3,227 |
| 2023 | 5 | 409 | 11,603 | 14,990 | 2,888 |
| 2022 | 5 | 410 | 11,396 | 13,611 | 2,915 |
| 2021 | 8 | 347 | 31 | 36 | 9 |

2,312 fixtures, 53,093 appearances, 3.56 million player-minutes, 7,748 goals,
6,499 players across 53 clubs. Player-level recording begins in 2022; 2021
predates the schema change and has results only.

## How it works

**The source is an API, not HTML.** The federation's site is a Vue single-page
application rendered from a Cockpit CMS instance, so there is no page scraping —
the data arrives as JSON. The read token is one the site ships to every browser;
this client reads it out of the site's own `common.js` at runtime rather than
hardcoding it, so a rotated token is picked up automatically and no credential
lives in this repository. Requests are throttled and every response is cached, so
re-running costs nothing.

**Minutes are reconstructed, not recorded.** The federation stores a starting
eleven, a bench and timed substitutions, and never a minutes-played figure. The
whole point of the exercise — any per-90 metric — depends on deriving it, and the
edge cases are where the interesting bugs live:

- Substitution times are free text entered by match officials: a plain number, the
  half-time marker `HT`, stoppage time as `90+2`, and at least once a superscript
  `90⁺5`. All four appear in the real data and all four parse.
- A player sent off leaves the pitch at the minute of the red card. The
  substitution list does not record it, so without handling cards separately a
  dismissed player is credited with the full match.
- An unparseable time is skipped rather than guessed, and the affected player
  keeps a defensible default instead of a fabricated one.

**What the undocumented columns mean.** Shot counts are stored under four keys
named `first` to `fourth`. Checking every season shows `third` is non-zero only in
knockout ties that went to extra time and `fourth` is never used at all, so they
are the two halves followed by the two extra-time halves. The schema names them
that way.

## Privacy

The squad lists carry names, kana, dates of birth, heights, weights and former
schools of amateur students. The federation publishing them is not the same as a
third party redistributing them, so the tool is built to make the safe thing the
easy thing:

- `--privacy aggregate` emits no per-player rows at all.
- `--privacy pseudonym` uses salted, non-reversible labels and states the residual
  risk on the report itself.
- `--privacy initials` exists and is **refused** for anything marked `--public`.
- `--public` refuses to write an unsafe file rather than warning about it.
- `ingest --drop-personal-data` deletes every name and squad detail, keeping only
  opaque ids. All the metrics still work; the tests assert it.

Initials are not anonymisation, and `privacy-check` measures rather than assumes
it. On the 2026 first division, of 189 players above 270 minutes, **105 (56%) are
unique on team, position and appearances alone** — three ordinary analytical
columns, against squad lists the federation already publishes. Removing the name
does not help. [docs/DATA_POLICY.md](docs/DATA_POLICY.md) has the full table and
the reasoning.

## Tests

```bash
python3 -m unittest discover -s tests -t . -v
```

103 tests, no network access, no fixtures taken from the federation — the test data
is invented clubs and invented people. CI runs them on Linux, macOS and Windows
against Python 3.9 and 3.13, and fails the build if any collected data is ever
committed.

## Licence

MIT — see [LICENSE](LICENSE). It covers this code. It says nothing about the
federation's data, which the tool does not redistribute.

## Not affiliated

An independent hobby project, not endorsed by or connected to the Tokyo University
Football Association. It reads only what their site already publishes. If they
would prefer it not to exist, open an issue and it comes down.
