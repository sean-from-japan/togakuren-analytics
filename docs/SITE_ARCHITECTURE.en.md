# Official site architecture and public API security assessment

*[日本語](SITE_ARCHITECTURE.ja.md)*

Observed: 10 September 2026 (Japan time)

## Conclusion

**Using an API is not itself a vulnerability or a defect.** A browser receiving
JSON from a server is an ordinary web architecture. Anything needed to render a
public page, including a token embedded in public JavaScript, is observable by
the visitor.

The implementation does, however, have observations to verify and hardening
opportunities separate from the choice to use an API:

1. An unfiltered `series` request made with the token shipped in public
   JavaScript returned one `published:false` record. Its ID and content were not
   inspected or stored. That fact alone cannot distinguish an empty test record,
   a duplicate of already-public information, or a real draft, so it does not
   establish a vulnerability with material impact. It is an observation whose
   publication intent should be confirmed with the operator.
2. On the match page, `seriesTeams` returns whole member objects, including
   `birthday`, `height`, `weight`, `formerTeam`, `nationality`, and `note`, even
   though that view does not need them. However, the official team pages
   intentionally publish names, kana, class, birthday, height, weight, former
   team, and notes in their roster tables. This is a response-minimisation and
   bulk-collection issue, not a confirmed new disclosure of confidential data.
3. The API permits any CORS origin and advertises `PUT` and `DELETE` as allowed
   methods. This does not prove that the public token may write, but it is broader
   than a public read client needs.
4. The API server disclosed `PHP/7.4.2`. Upstream support for PHP 7.4 has ended;
   the actual package and any distribution backports need to be checked.
5. The browser receives Vue 2.7.10, Axios 0.21.1, and Lodash 4.17.20. Vue 2 is
   end-of-life and all three dependencies need a current dependency review.

The short assessment is therefore: **the API architecture is normal and most
roster attributes are already intentionally published. One `published:false`
record is returned, but without its contents or the operator's intended API
contract this is an observation to verify, not a confirmed vulnerability.**

## Architecture

The accurate description is a **Vue 2 match application embedded in a page
served by WordPress**, rather than the whole site being a pure Vue SPA.

```mermaid
flowchart LR
    U[Visitor's browser]

    subgraph WWW[www.f-togakuren.com]
        WP[WordPress 7.1<br/>HTML, articles and theme]
        JS[Theme JavaScript<br/>common.js, match.js, components]
        REST[WordPress REST API<br/>past-results page]
    end

    subgraph CDN[Third-party CDNs]
        LIB[Vue 2.7.10<br/>Axios 0.21.1<br/>Day.js, Lodash, Hooper]
    end

    subgraph DATA[data.f-togakuren.com]
        API[Cockpit CMS API<br/>collections/get/*]
        DB[(Competitions, games,<br/>teams and squads)]
        ADMIN[Cockpit administration]
    end

    U -->|GET /match| WP
    U -->|GET common.js and page scripts| JS
    U -->|GET libraries| LIB
    JS -->|Configure API URL and public Bearer| U
    U -->|POST + Bearer + JSON query| API
    U -->|GET /wp-json/wp/v2/pages/496| REST
    API --> DB
    ADMIN --> DB
```

`www` and `data` are separate origins. `common.js` configures Axios to send API
requests to `data.f-togakuren.com` with a Bearer token. That value must be treated
as a public-client identifier rather than a secret.

## Page-load traffic

```mermaid
sequenceDiagram
    participant B as Browser
    participant W as WordPress / www
    participant C as CDN
    participant A as Cockpit API / data

    B->>W: GET /match
    W-->>B: HTML containing Vue templates
    B->>C: Vue, Axios, Day.js, Lodash, etc.
    C-->>B: JavaScript libraries
    B->>W: GET common.js, match.js, components
    W-->>B: API URL, public Bearer, UI logic
    B->>A: POST /api/collections/get/series
    Note right of B: published:true, last 20 years
    A-->>B: years and series
    B->>A: POST /api/collections/get/series
    Note right of B: selected series, published:true
    A-->>B: competition settings
    B->>A: POST /api/collections/get/games
    Note right of B: seriesId, published:true, populate:1
    A-->>B: fixtures, results and match records
    B->>A: POST /api/collections/get/seriesTeams
    A-->>B: clubs, table and members
    opt Tournament
        B->>A: POST /api/collections/get/blocks
        A-->>B: bracket
    end
    B->>B: Vue renders fixtures, table, scorers, cards and detail
```

The ranking component makes another `seriesTeams` request and the discipline
component makes another `games` request. The past-results modal alone reads a
page from the same site's WordPress REST API rather than Cockpit.

## Information exchanged

| Source | Main filter | Used by the page | Additional response fields observed |
|---|---|---|---|
| `series` | year, `published:true` | name, short name, type, rules | creator/editor IDs, internal order, descriptive text |
| `games` | `seriesId`, `published:true`, `populate:1` | date, venue, teams, scores, cards, lineups, substitutions, shots | officials, referees, internal metadata, lock state |
| `seriesTeams` | `seriesId` | on the match page: team, table, name, number, position | birthday, kana, class, height, weight, former team, nationality and notes; all but some fields such as nationality are displayed on official team pages |
| `blocks` | series ID | tournament bracket | may include internal metadata |
| WordPress REST | fixed page ID 496 | rendered past-results body | public WordPress page representation |

The response is wider than the match page that receives it. Names, kana, class,
birthday, height, weight, former team, and notes are nevertheless intentionally
displayed on the official team pages, so retrieving those fields through the API
is not by itself a leak of unpublished information. Returning more fields than a
particular view needs still makes bulk collection cheaper, and OWASP recommends
response minimisation rather than client-side filtering.

## Security boundary

### The API itself

The API is not the problem. Both server-rendered HTML and client-rendered JSON
must deliver public information to the visitor. An API can make the boundary
cleaner and separate presentation from content management.

### The Bearer token in JavaScript

Its presence alone is not secret leakage. A fixed browser token is obtainable by
everyone and must be designed as a public value. Safety must come from a
read-only, least-privilege role; server-enforced publication state; an allowlist
of collections and fields; separation from editor credentials; and rate limits,
monitoring, and rotation. Cockpit's own documentation recommends a dedicated
role for public API access.

### Findings

| Priority | Observation | Assessment | Why |
|---|---|---|---|
| High | API banner says `PHP/7.4.2` | Verify and update | PHP 7.4 reached upstream EOL on 28 November 2022. A banner cannot show whether Debian security fixes were backported. |
| Informational/Low | Public token returned one `published:false` series | Needs confirmation | The UI condition is not server-enforced, but confidentiality impact cannot be determined without the contents and the operator's intended API contract. |
| Low | Match-page `seriesTeams` returns personal attributes unused by that view | Response minimisation gap | Most are already public on official team pages, so no new confidential-data exposure is confirmed. It still lowers the cost of bulk collection. |
| Medium | Vue 2.7.10 and old Axios/Lodash | Maintenance and supply-chain risk | Vue 2 is EOL. The observed code alone is not enough to claim immediate exploitability. |
| Low | CORS `*` and all main HTTP methods advertised | Configuration should be narrowed | CORS is not authorisation, and advertising `DELETE` does not prove the token can delete. |
| Low | No CSP, HSTS, nosniff or anti-framing header observed | Missing defence in depth | These headers were absent from the `/match` response observed on 10 September 2026. |
| Low | Exact Apache and PHP versions disclosed | Information exposure | Useful for reconnaissance, but not an intrusion by itself. |

No write, delete, privilege-escalation, or admin-login attempt was made. The
public token's write permissions remain unknown. An `OPTIONS` response listing
`PUT` and `DELETE` must not be reported as proof of write access.

## Recommended target

```mermaid
flowchart LR
    B[Browser]
    P[Public API / BFF]
    V[(Published view<br/>required fields only)]
    C[(Cockpit source<br/>drafts and personal fields)]
    A[Administration]

    B -->|Anonymous or short-lived public key<br/>GET-oriented, rate-limited| P
    P -->|Force published=true<br/>fixed query and schema| V
    C -->|Publication projection| V
    A -->|Strong authentication, separate origin| C
```

Recommended order:

1. Audit the role behind the public token. Allow only required
   `collections/get` routes and explicitly deny save, remove, administration,
   and asset-write routes.
2. Enforce `published:true` on the server rather than trusting a client filter.
3. Define fixed public response schemas: retain the detailed roster for the
   official team page while returning only name, number, position, and other
   required fields to the match page.
4. Confirm whether returning `published:false` records is intentional. If not,
   remove them from public API access and rotate the token only if its role was
   broader than intended.
5. Upgrade PHP, Cockpit, Vue, Axios, and Lodash to supported versions.
6. Restrict the browser origin and methods to those actually required, without
   treating CORS as authentication or authorisation.
7. Add API rate limits, response-size limits, monitoring, and bulk-enumeration
   alerts.
8. Consider CSP, HSTS, `X-Content-Type-Options: nosniff`, `frame-ancestors` or
   `X-Frame-Options`, and reduced server banners.

## Change in this repository

To respect the same public boundary as the visible site, `Client.series()` now
always sends `published:true` and requests only the series fields needed by the
analysis. Games already used `published:true`. Responses remain cached locally
and requests retain the default 0.5-second spacing.

This change makes the repository honour its own policy of fetching published
content only. The official API still accepts unfiltered queries, but whether
that is a defect or intended behaviour cannot be determined without the record
contents and the operator's publication policy.

## Method and limits

The assessment read the `/match` HTML and headers, its `common.js`, `match.js`,
five UI component scripts, `robots.txt`, API-root and CORS responses, one minimal
unauthenticated request, the key names from one published series, and only the
counts of `published` values in the unfiltered series response. Official team
pages were also checked to distinguish intentionally displayed roster fields
from API-only fields.

The token value, unpublished record ID and contents, and player values were not
stored in this document or repository. No scanner, load test, write/delete
request, privilege escalation, or admin intrusion was attempted. This is a
limited external observation, not a full audit of server configuration and logs.

## References

- [Tokyo University Football Association: fixtures and results](https://www.f-togakuren.com/match)
- [Tokyo University Football Association: privacy policy](https://www.f-togakuren.com/privacy-policy)
- [Tokyo University Football Association: example team page](https://www.f-togakuren.com/teams/427)
- [Cockpit CMS: Authentication](https://getcockpit.com/documentation/core/api/authentication)
- [Cockpit CMS: Configuration](https://getcockpit.com/documentation/core/quickstart/configuration)
- [OWASP: API3:2019 Excessive Data Exposure](https://owasp.org/API-Security/editions/2019/en/0xa3-excessive-data-exposure/)
- [MDN: CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [PHP: Unsupported Branches](https://www.php.net/eol.php)
- [Vue 2 Has Reached End of Life](https://v2.vuejs.org/eol/)
- [Axios security advisories](https://github.com/axios/axios/security/advisories)
- [Lodash changelog](https://github.com/lodash/lodash/wiki/Changelog)
