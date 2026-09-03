# Why this league

*[日本語](SOURCE_SELECTION.ja.md)*

University football in Japan is organised in a pyramid: prefectural leagues at the
bottom, regional leagues above them, and a national championship at the top. This
project reads one rung of it — the Tokyo University Football Association, which
runs the Tokyo and Kanagawa university leagues. That was a choice, and it was made
on two things that can be checked rather than argued about: **what each federation
actually publishes, and what its site says about being read by a program.**

Checked 2026-09-01.

## What this federation publishes

| | |
|---|---|
| Transport | JSON from a Cockpit CMS. No HTML parsing, so no breakage when the page design changes. |
| Depth | Starting eleven, bench, timed substitutions, cards with offence codes, per-player shot counts by period, squad lists. |
| History | 2,312 fixtures back to 2021; player-level records from 2022. |
| `robots.txt` | Disallows `/wp-admin/` only. |

The depth is what makes the analysis possible. Every result in
[FINDINGS.en.md](../FINDINGS.en.md) — the preseason model built on the squad
lists, what a division change does to predictability, the year-group study —
needs squad and match-level records for several seasons. Results tables alone
would not produce any of them.

## The tier above: the Kanto regional league

The obvious way to grow this project is upward, to the Kanto University Football
League — 36 universities, a higher standard, and the division several clubs in this
dataset are trying to reach. It is not done here, for a reason that has nothing to
do with difficulty.

The federation's own site, `jufa-kanto.jp`, allows crawling (`Allow: /`). But every
link to results, standings, cross-tables, scorers, assists and disciplinary lists —
for every season from 2012 to 2026 — points to a third-party league management
system at `football-system.jp`, and that host's `robots.txt` reads:

```
User-agent: *
Disallow: /
```

Which settles it. A repository whose whole argument is that publication and
redistribution are different things does not get to ignore a site telling every
program to stay out.

Two secondary points make the decision easier rather than harder:

- The fixture lists on that system carry **scores only**. There are no per-match
  record pages, so the lineups, minutes and shot counts this project is built
  around are not there to be had in the first place.
- The federation does publish match reports on its own site for the current
  season, with results, scorers, and an explicit home/away marking that the Tokyo
  data lacks. But only the current season: earlier years return 404. One season of
  results and scorers extends none of the analyses above.

If that data is ever wanted, the way to get it is to ask the federation, not to
work around a `Disallow`.

## The tier below and beside

The Kanagawa prefectural university league publishes standings as plain HTML with
no crawling restriction, but standings only — no fixture-level record. Not enough
to support anything here.

## What this leaves

As far as could be found, no open-source project covers Japanese university
football at match level; the established football data libraries aggregate
professional leagues and do not reach it. So the pyramid has exactly one rung that
is both deep enough to analyse and open to being read by a program, and this is a
tool for that rung.

That is a narrower claim than "the best league to study". It is the honest one.
