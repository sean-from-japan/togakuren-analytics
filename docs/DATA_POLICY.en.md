# Data policy

*[日本語](DATA_POLICY.ja.md)*

The people in this dataset are amateur student athletes. This document records
what the tool collects, what it will not let you publish, and why the defaults
are set the way they are.

## The source

The Tokyo University Football Association (東京都大学サッカー連盟) publishes
fixtures, results, squad lists and match records at
[f-togakuren.com](https://www.f-togakuren.com/match). The site is a Vue
single-page application; its pages are rendered from a Cockpit CMS instance at
`data.f-togakuren.com`, reached with a read token that the site ships to every
browser in `common.js`.

This tool discovers that token the same way a browser does instead of hardcoding
it, requests only content the site already renders publicly, sleeps between
requests, and caches every response so a re-run costs nothing. `robots.txt`
disallows only `/wp-admin/`, and the site's privacy policy places no restriction
on reading published pages.

None of that makes the *contents* freely redistributable, which is the rest of
this document.

## This repository contains no collected data

There are no fixtures, no squad lists and no exports committed here — only code,
synthetic test fixtures with invented names, and this policy. `data/` and
`reports/` are ignored by git.

That is the ordinary pattern for scraping libraries: [soccerdata][sd] and
[worldfootballR][wf] ship extraction code and leave the collected data on the
user's machine. It is also the only pattern that avoids the problem below.

[sd]: https://github.com/probberechts/soccerdata
[wf]: https://github.com/JaseZiv/worldfootballR

## Why redistribution is the line, not collection

Under Japan's Act on the Protection of Personal Information (個人情報保護法),
information does not stop being personal data because someone else published it
first. Names, dates of birth, heights and former schools identify specific
individuals whether they sit on a federation website or in a CSV on GitHub.
Providing that data to third parties is regulated (Art. 27) and generally needs
the individual's consent.

Statistical information is different. The Personal Information Protection
Commission's own guidance is that data aggregated across multiple people, with
the correspondence to specific individuals removed, is not personal information
at all and falls outside the Act:

- [統計情報と匿名加工情報の違いは何ですか](https://www.ppc.go.jp/all_faq_index/faq1-q15-2/)
- [統計情報としてB社に提供した場合、B社においては個人情報に該当しますか](https://www.ppc.go.jp/all_faq_index/faq1-q1-17/)

So the practical rule this tool enforces is:

| Where it goes | What may be in it |
|---|---|
| Local database and reports | Everything. Personal analysis of published material. |
| Anything published | Group aggregates, or pseudonymous per-player rows with the residual risk stated. |
| This repository | Code only. |

This is a design constraint, not legal advice.

## Initials are not anonymisation

Replacing 山田 太郎 with `山.太.` feels like protection and mostly is not. The
squad lists are public, the divisions have twelve teams, and the columns an
analysis needs — team, position, appearances — are themselves identifying.

`privacy-check` measures this instead of assuming it. On the 2026 first division,
189 players above 270 minutes:

| Quasi-identifiers | k | Rows unique on them |
|---|---|---|
| team | 13 | 0 of 189 (0%) |
| team + position | 1 | 17 of 189 (9%) |
| team + position + appearances | 1 | 105 of 189 (56%) |
| team + position + appearances + goals | 1 | 146 of 189 (77%) |

`k = 1` means at least one row is unique on those columns, so it can be matched
back to a named person using the federation's own squad lists — whatever the name
column has been replaced with. More than half the table is uniquely identifiable
from three ordinary analytical columns.

## The school column is the one that finishes the job

`squad_members.former_team` holds the high school or club youth side a player
arrived from. It is filled in for 97% of squad rows and it is the input to the
preseason model in [../FINDINGS.en.md](../FINDINGS.en.md), so it is worth being
exact about what it costs:

| Quasi-identifiers | k | Rows unique on them |
|---|---|---|
| school | 1 | 73 of 189 (39%) |
| team + school | 1 | 106 of 189 (56%) |
| team + position + appearances + school | 1 | 184 of 189 (97%) |

The school on its own identifies two players in five. Added to the three columns
any analysis already wants, it takes the division from 56% unique to **97%** —
effectively every row. Pseudonyms cannot survive that, so the rule is not "be
careful with it":

- **No per-player output carries a school**, in any privacy mode, including
  `pseudonym`.
- Club-level aggregates of it are fine, and are what the preseason model
  publishes: a squad's average, never a player's row.
- A per-school table has to pool every season and drop schools with fewer than
  five players. In a single division of one season, 95% of the schools present
  have fewer than five, so that table does not exist.

Run it on your own extract:

```bash
python3 -m togakuren privacy-check --series "1部"
```

## What the tool does about it

- `--privacy full` is the default for local reports and is refused for anything
  marked `--public`.
- `--privacy initials` exists, and is also refused for `--public`. It is offered
  because it is what people reach for, and rejected because the table above is
  what it actually buys.
- `--privacy pseudonym` replaces names with salted, non-reversible labels. A
  fresh salt is generated per run unless you pass one. Reports built this way
  carry a banner stating how many rows are still unique on team and position, so
  the residual risk travels with the file.
- `--privacy aggregate` emits no per-player rows at all. This is the mode whose
  output is statistical information in the sense above.
- `ingest --drop-personal-data` deletes names, kana, birth-adjacent squad detail
  and manager names after loading, keeping only opaque player ids. Every metric
  in this tool still works afterwards; the tests assert it.

[PLAYER_ANALYSIS_SAMPLE.en.md](PLAYER_ANALYSIS_SAMPLE.en.md) shows what the player-level
output actually looks like, over an invented season with no real person in it.

## Rate limiting and takedown

The default delay between requests is 0.5 seconds and responses are cached on
disk, so a full five-season backfill is a few hundred requests once. Do not
remove the delay.

If the federation, or any club whose results appear here, would prefer this tool
not to exist, open an issue and it will be taken down. Nothing here is worth being
a nuisance over.
