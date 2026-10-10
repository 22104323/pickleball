# Reclub Integration — Attendance, Ratings, Anti-Stacking Balance

Courtside is a local organizer workspace for pickleball open play. Check in the
players who are physically present, build balanced doubles games, and keep the
rotation moving without pairing the strongest two against the weakest two when
a better valid split is available.

> Attendance drives the queue. Ratings drive balance. History drives fairness.

## Current status

This repository now contains a working local MVP, not a deployed club service.
It uses Python's standard library, SQLite, and plain HTML/CSS/JavaScript. There
are no runtime packages to install and no build step.

| Available now | Pending |
| --- | --- |
| Session creation, court count, capacity, and eight play modes | Supported Reclub API/webhook contract and hosted live sync |
| Pasted player lists, local Reclub preview, and a gated read-only single-event website feed | Supported Reclub developer contract, verified export format, and upstream write-back |
| Separate RSVP, attendance, eligibility, and queue states | Payments, guests, division policies, and notification integrations |
| Manual check-in, late-arrival tracking, pause, rejoin, and check-out | Attendance reliability rewards and approved future-session penalties |
| Transactional mode-aware court assignment, partner preferences, starts, corrections, and Rebuild | Winner-stays, manual match editing, and multi-court swap optimization |
| Recent partner/opponent costs and a small first-game newcomer bonus | Full fairness dashboard and calibrated match-quality metrics |
| Session-close Glicko-2 periods, rating history, and audit records | Empirical validation of the individual doubles adaptation |
| Responsive organizer interface, local Live View, reduced-motion support, and random same-browser session links | Hosted organizer authentication, authorization, and multi-organizer access |
| GitHub review rules, CI checks, and a gated Vercel deployment workflow | Vercel connection, approval to publish a selected event's attendee fields, and hosted organizer access controls |

## Contributions and deployment

This repository is public; that does not grant upstream write access. Contributors
can fork it, push to their fork, and submit a PR to `main`. GitHub requires a PR and
the `verify` check, blocks force pushes and deletion, and has no bypass actors. The
sole maintainer `@22104323` can merge after checks pass; an approval count is not
required because there is no independent reviewer. Development and staging branches
are kept in a private companion workspace; public releases land on `main`. See
[CONTRIBUTING.md](CONTRIBUTING.md).

Public staging and production deployments require a separate owner approval. The
read-only attendee endpoint and hosted page are implemented, but the Vercel workflow
is still **not live**: the Vercel project is not connected, no event is configured,
and public display of attendee names and avatars has not been approved. The workflow
continues to block deployment until those checks are complete. [Deployment setup and
Reclub findings](docs/deployment.md) describe the settings, prerequisites, and
limitations. The local organizer continues to work independently.

`.env` files, credentials, databases, and local Vercel metadata are ignored and
checked before commits/pushes. `.gitignore` and `.vercelignore` themselves are public
so every contributor shares these rules. GitHub secret scanning and push protection
are enabled; no scanner guarantees detection of every secret. Use
[private security reporting](SECURITY.md) for vulnerabilities.

The code uses the [MIT license](LICENSE); code reuse does not grant repository write
access. Project instructions are portable in [AGENTS.md](AGENTS.md) and [CLAUDE.md](CLAUDE.md).

## Run locally

Use Python 3.11 or newer with SQLite 3.35 or newer:

```sh
python3 -m picklequeue.server
```

Open `http://127.0.0.1:8080`. The server binds to loopback only and accepts local
hostnames; it is a single-operator tool, without a login system. Do not expose it
as a public service. Hosted use needs a reviewed access model.

The database is created at `data/pickleball.sqlite3` and survives server restarts.
`data/` is ignored by Git. To select another port or database:

```sh
python3 -m picklequeue.server --port 8081 --database data/another-session.sqlite3
```

The local organizer page has a **Generate Link** button. It creates an **Open Play** session and
puts a random UUID in the URL fragment. A mapping from that token to the local session
is kept in this browser's local storage. The link works in the same browser profile on
the same origin only; it is not an account, a password, or cross-device sharing. Clearing
browser storage loses the link mapping. Session records remain in the local SQLite
database across server restarts; they are not uploaded to a hosted session store. The
local server serves the organizer at `/` and `/index.html`. Vercel serves a separate
read-only attendee page and excludes the organizer page and its JavaScript.
The organizer landing screen uses a locally served Patrick Hand font; its SIL Open Font License
is included in [web/fonts/OFL.txt](web/fonts/OFL.txt).

Start with a new session. Import a roster or select **Load demo roster**, which
creates 30 clearly marked synthetic players in an empty session. Demo identities
are isolated from real roster imports. In **Attendance**, confirm eligibility
and check players in; then **Fill open courts**. Start each game explicitly,
choose **Team 1 Wins** or **Team 2 Wins** when finished, and close the session
to finalize ratings.

Session sections appear as buttons in the left navigation rail on desktop and a compact
button row on mobile. Individual skill levels are set by clicking a star; arrow keys move
between levels, and the **Clear** control removes a single player's rating. The bulk
level dropdown remains available for selected players.

The session workspace uses a compact top header, session selector, and left-side
navigation buttons. Live Courts appear above the rotation: the ordered Queue sits on the left,
with separate numbered Up Next cards beside it. Queue rows include reserved players
until their game starts; the occupied-court counter counts only games actually playing.
Use **Start Up Next** on a court or **Send to Court** on its reserved card to start it.
On narrow screens, Up Next appears before the queue. There is one reserved plan per
available court, not an independent list of future matches. Manual team editing,
dynamic court management, and player-call controls remain pending.

## Reclub ownership and integration boundary

Reclub is the intended source of truth for club identity, event details, and
RSVPs. Its public site describes club management, attendance, payments, and meets
with RSVPs and waitlists. This confirms product capabilities, not an integration
contract. [Reclub product overview](https://reclub.co/)

A supported developer contract, webhook event names, authentication scheme, pagination,
rate limits, check-in endpoints, and write-back permissions have not been verified.
The local app offers an optional, read-only preview that calls the observed public
`/meets/by-ref/{referenceCode}` and batch profile endpoints. It accepts only HTTPS
links on `reclub.co`, uses fixed API paths, and never asks for Reclub credentials.
This is a compatibility adapter, not an official or guaranteed integration. It does
not scrape HTML or send changes upstream. The CSV below is **this engine's input
format**, not a claimed Reclub export.

A read-only compatibility check on 2026-10-10 verified the supplied public
`/meets/by-ref/{referenceCode}`, batch profile, and group activity endpoints. This
supports the local event preview, not a completed hosted integration or a service
guarantee. The supplied club-slug endpoint returned 404. The participant records
did not contain an explicit check-in field; sign-ups must not become automatic
physical attendance. Guest slots remain separate from an inviter's profile. Review
the roster before adding it; only selected player names, IDs, and optional organizer
fields are written to this computer's SQLite session database. A separate read-only
Vercel feed is implemented for one event selected with `RECLUB_EVENT_REF`; it does not
write to SQLite. It is not live until an actual public event is selected and the owner
confirms that publishing its attendee names and approved avatar URLs is appropriate.
See [the observed response shape and deployment plan](docs/deployment.md).

| Concept | Current representation | Authority |
| --- | --- | --- |
| Member | Local `members` keyed by source, club identifier, external ID | Reclub remains upstream identity authority; no email-based merges |
| Event | Local `sessions` with start instant, courts, and capacity | Organizer-entered for this MVP; external event mapping pending |
| RSVP | `roster.rsvp` | Imported intent; never equivalent to presence |
| Check-in | `roster.checked_in_at` and attendance | Local organizer observation until a verified upstream check-in exists |
| Eligibility | Membership and waiver fields | Explicit imported or organizer-confirmed values; unknown blocks play |
| Court activity | Games, participants, and results | Queue engine |
| Rating and pairing history | Member ratings and completed games | Queue engine; never overwritten by a roster reimport |

If upstream check-in is unavailable, local attendance is a clearly identified
operational record. The app must not claim that Reclub confirmed it. Payment,
waiver, membership-expiry, and notification fields must be verified independently
before treating them as available upstream facts.

The local preview includes account profiles when available and named guest slots
when the observed event response supplies a guest name. Unnamed guests are labelled
for organizer review; they are not represented as the inviting member. Local imports
do not copy avatars, phone numbers, or email addresses. The hosted feed may display
only profile names and HTTPS avatar URLs from two allow-listed Reclub image hosts,
along with event title, participant-slot ID, and status 1. It does not persist a
roster. A sign-up is not a check-in; attendance remains a local organizer record.

### CSV input

Required headers: `external_id,name,rsvp,membership,waiver`.
Optional header: `initial_rating`, used only when creating a new member.

```csv
external_id,name,rsvp,membership,waiver,initial_rating
sample-a,Player A (sample),yes,active,valid,1800
sample-b,Player B (sample),yes,active,valid,1750
sample-c,Player C (sample),yes,active,valid,1200
sample-d,Player D (sample),yes,active,valid,1150
```

These are synthetic values. A ready-to-import example is
[examples/roster.csv](examples/roster.csv).

- RSVP accepts `yes`, `no`, `waitlist`, or `cancelled`.
- Membership accepts `active`, `expired`, or `unknown`.
- Waiver accepts `valid`, `missing`, or `unknown`.
- Supply a stable club identifier and external player IDs. Renaming a player does
  not create a new identity; duplicate IDs in a file are rejected.
- Import at most 200 rows and 200 KB. Validation is atomic: a bad row rolls back
  the entire import.
- Reimporting updates names, RSVP, and eligibility, while preserving check-ins,
  queue position, results, and established ratings. Omitted players are retained;
  an incomplete export must not silently check someone out.
- An eligibility revocation removes a waiting player. Revoking an assigned or
  playing player requires resolving their game first; that import is rejected
  with a clear error and no partial changes.
- Phone numbers, email addresses, and unnecessary personal data are not imported.

### Future sync contract

Before implementing live Reclub sync, obtain an authorized contract and sample
payloads. Map each recurring event occurrence to a distinct external event key.
Store source delivery IDs, versions/cursors, and observed times separately from
local audit IDs. Handle duplicates, out-of-order delivery, retries, pagination,
partial snapshots, deletions, event cancellations, and timezone conversions.

Polling must resume from a durable cursor with overlap and deduplication; polling
only the last five minutes would lose updates after a longer outage. Missing records
in a partial page are not deletions. Absence and penalties must not be inferred
from failed synchronization. Write-back remains off until its supported contract
and permissions are approved. Reclub messages never update a rating by themselves.

## Attendance and eligibility

Presence, registration, and rotation are independent dimensions. `GUEST`, `BLOCKED`,
and `PLAYED` are not interchangeable lifecycle states: guest is an identity type,
blocked is an eligibility decision, and played is recorded game history.

| Dimension | Values |
| --- | --- |
| RSVP | `yes`, `no`, `waitlist`, `cancelled` |
| Attendance | `absent`, `present`, `left`, `no_show` |
| Queue | `off`, `waiting`, `assigned`, `playing` |
| Game | `assigned`, `playing`, `completed`, `cancelled` |

Normal flow:

```text
RSVP yes + absent + off
  -> organizer check-in
  -> present + waiting (if eligible)
  -> present + assigned
  -> explicit game start
  -> present + playing
  -> completed result, games_played increases
  -> present + waiting, new ticket at the back
```

Check-in records presence even when eligibility is unknown; the player stays out
of the queue until membership is active and the waiver is valid. A walk-in with
RSVP `no` or `waitlist` can be admitted by the organizer's explicit check-in,
subject to capacity and eligibility. RSVP import alone cannot admit anyone.

Arrival later than `starts_at + 15 minutes` is marked late. At exactly 15 minutes,
the player is on time. Late arrivals get a new queue ticket at the back, without
a hidden balance override.

At or after `starts_at + 30 minutes`, reconciliation marks only RSVP-yes players
who **never** checked in as no-shows. A later check-in changes that operational
state to present and records late arrival. A player who checked in and left is
not a no-show. Session closing performs the same classification if the threshold
has passed. No warnings, bans, deposits, or future-session penalties are sent or
applied in this MVP.

Pausing drops the player out of the queue while keeping them present. Rejoining
gets a new ticket. Check-out removes the player from the queue. Resolve an assigned
or playing game before a participant leaves: cancel an incomplete game with a
reason, then check the departing player out. Incomplete games never affect ratings.

## Queue and anti-stacking algorithm

Hard validity checks happen at the engine boundary:

- Exactly four distinct, physically present, eligible players per doubles game.
- Two players on each side and a valid court in the session.
- A player cannot have two active assignments; a court cannot host two active games.
- A session's checked-in capacity cannot be exceeded.
- Assigned games start only after an organizer action.

Each free court is filled sequentially from players ordered by increasing queue
ticket. The longest-waiting player is mandatory. Evaluate combinations from the
first 12 waiting players and all three unique 2v2 splits of each four-person set.
If none is acceptable, expand once to the first 16. Four played players are removed
before the next court is assigned. Ties are deterministic.

### Play modes and partner preferences

Session setup offers Balanced, Social Mix, Skill Separated, Winners / Losers,
Skill Courts, King/Queen, and Club Wars. Mixed Doubles is shown disabled in the
skills-only setup, since it requires player categories. Each court fill still
requires four present and eligible players. Social Mix scores recent partner and
opponent repetition without using ratings. Skill modes restrict candidate pools
to one configured rating band. Mixed Doubles requires two organizer-confirmed
men and two women, one of each on each team; names are never used to infer a
category. Club Wars requires organizer-assigned groups and puts one group on each
side. Winners / Losers uses each player's most recent completed result, while
King/Queen moves winners toward court 1 and losers toward higher-numbered courts.

The roster review screen supports selected players, name edits, optional skill
levels, and partner preferences. No gender field is shown or submitted by this UI.
A chosen pair is kept together as a hard team
constraint; the second player can be included beyond the normal candidate window
when needed. If that conflicts with the selected play mode or no other valid
match exists, the court stays open with an explanation. Attendance also offers
pair/unpair controls. “Check in all” affects RSVP-yes players only; each check-in
is still local organizer-recorded presence. Approximate DUPR labels map to this
engine's 1000–1800 rating scale and are not official DUPR conversions.

The engine protects the oldest player rather than indefinitely selecting other
easy-to-balance groups. If no acceptable game includes them, it reports the reason
and leaves the court unassigned. The organizer can arrange a suitable pool or
explicitly pause a player; the engine does not silently demote them.

### Result corrections, Up Next, and Live View

Assigned games are this engine's reserved Up Next plans: each holds one open court
and four eligible players until explicitly started or cancelled. In **Game results**,
**Swap winner** opens inline **Cancel** / **Swap** controls. Cancel does not write
anything. Swap reverses the recorded winner in the same game and audits the
before/after outcome. Match number, court, completion time, total game count, games
played, queue tickets, and existing reserved teams stay unchanged.

**Live Standings** derive wins/losses from completed results and update immediately.
The most recent winner/loser labels also reflect corrections. A staged plan's labels
can therefore change while its teams remain reserved. **Rebuild** is a separate,
explicit action on an unstarted game. It reuses the same mode-aware assignment
engine with corrected history, includes the released players at their existing wait
priority, and excludes the previous team split. Other courts remain reserved. If no
alternative valid game exists, the entire change rolls back, keeping the old plan
and revision. Rebuild neither starts a game nor relaxes eligibility, pairing, balance,
or division constraints. Completed or playing games cannot be rebuilt.

Corrections are available only while the session is active. Ratings remain frozen
until close, when the corrected outcomes supply the single Glicko-2 period. Closed
sessions are read-only; reopening and replaying finalized ratings remain pending.

**Live View** displays courts and standings without court mutation controls. It is
an organizer presentation view on this computer, not a club/cloud sharing service
or a separate authorization boundary. It refreshes from the local server using the
same polling lifecycle as the workspace.

### Rating scale and cost

Use **team means** consistently, not sums in one place and means in another:

```text
team_mean = (player_1_rating + player_2_rating) / 2
team_delta = abs(mean_a - mean_b)
expected_a = 1 / (1 + 10 ** ((mean_b - mean_a) / 400))

valid balance: team_delta <= 150 AND 0.40 <= expected_a <= 0.60

cost =
  8 * team_delta / 75
  + 4 * average_internal_partner_gap / 350
  + 3 * recent_partner_count
  + 2 * recent_opponent_count
  + skipped_wait_positions
  - first_game_newcomer_bonus
```

`skipped_wait_positions` is the quartet's zero-based positions summed minus six;
the first four cost zero. Each provisional player playing their first game of
the session contributes `0.5` newcomer bonus, capped naturally at `2` for four
players. It cannot exclude the oldest player or bypass eligibility or balance.

Recent relationships come from the last ten completed games involving members
of this roster, including prior sessions with the same stable member identity.
Count the two teammate pairs and four opponent pairs, not only one team's partners.
Cancelled games are excluded. This is a simple recency window, not yet the proposed
per-player cooldown policy.

The logistic probability is a **pairing heuristic**, not a calibrated Glicko-2
doubles forecast. With equal ratings it estimates 50%; high uncertainty does not
mean a game is guaranteed competitive. Record pre-game estimates and evaluate
them against real results before claiming predictive accuracy.

### The supplied stacking example

| Split | Team sums | Team means | Mean delta |
| --- | --- | --- | --- |
| A 1800 + B 1750 versus C 1200 + D 1150 | 3550 / 2350 | 1775 / 1175 | 600 |
| A + C versus B + D | 3000 / 2900 | 1500 / 1450 | 50 |
| A + D versus B + C | 2950 / 2950 | 1475 / 1475 | 0 |

With only those four and no history, the third split wins. The first is invalid.
Internal partner gap is a **soft cost** here: a hard 600-point partner-gap cap
from the draft would reject A + D, whose gap is 650, contradicting the requested
zero-delta example. Do not add that hard cap without resolving this tradeoff.

Avoidable stacking means rejecting an inferior split when a better valid split
exists. It does not mean every outcome can be guaranteed close, or that two
high-rated veterans must always be forbidden to partner in an equal-strength pool.

## Ratings

The old `delta = K * (actual - expected)` formula is Elo. Changing K does not make
it Glicko-2. This implementation uses rating, deviation, volatility, and the
iterative volatility update, and checks the numerical routine against the
author's worked example. [Glickman's Glicko-2 specification](https://glicko.net/glicko/glicko2.pdf)

New players use the requested prior `1200 / 350 / 0.06`; an imported initial rating
can replace 1200 when first creating an identity. Self-ratings are priors, not
verified ability. A player remains provisional until ten rated games. There is
no automatic mapping from these numbers to DUPR or another official pickleball rating.

Ratings are frozen during an active session. Closing treats completed games as
one period, with all observations computed from pre-period snapshots. Results
immediately update queue/history; rating values update once at close. Repeated
completion or closing cannot apply the same result twice. Cancelling, no-shows,
and attendance changes never create rating results.

### Individual doubles adaptation

Canonical Glicko-2 describes head-to-head competitors. For individual doubles,
this MVP uses an explicit approximation: each player's effective opponent is
the two opposing ratings summed minus their partner's rating. Its uncertainty
combines the opposing players' and partner's deviations by root-sum-square.
Each completed team win/loss supplies one observation to each player, not two
independent opponent outcomes.

That adaptation is experimental; it is not the author's canonical doubles model.
Validate partner effects and prediction quality before competitive ranking use.
No ad hoc K factor or margin multiplier is added. The core helper supports
inactive-period uncertainty growth, but calendar-based inactivity updates are
not scheduled in this MVP. App rating bounds are 0–4000 and deviation is capped
at 350 after a played period.

Members cannot check into a second active session while present in another, or
while that other session has unfinalized played games. Closing rejects stale
rating snapshots rather than overwriting another period's results.

## Persisted schema and consistency

[picklequeue/schema.sql](picklequeue/schema.sql) is the actual SQLite schema.
It is not a PostgreSQL migration. A database/backend change remains separate work.

| Table | Purpose and constraints |
| --- | --- |
| `sessions` | Start instant, courts, capacity, status, queue ticket counter, revision |
| `members` | Stable `(source, club_key, external_id)` identity; current rating/RD/volatility |
| `roster` | One member per session; independent RSVP, attendance, eligibility, queue state; pre-period snapshots |
| `games` | Court, state, scores, pre-game means/probability/cost; one active game per court |
| `game_players` | Team side and frozen player values; one occurrence per player per game |
| `active_assignments` | Unique active assignment per roster entry |
| `rating_history` | One before/after rating record per member per session |
| `audit_log` | Local action, time, target IDs, and cancellation reasons |

Every session mutation uses `BEGIN IMMEDIATE` and compares its revision. Two tabs
trying the same assignment cannot both succeed; the stale one gets HTTP 409 and
refreshes. Database uniqueness backs court/player reservations. Check-ins,
capacity, eligibility, game state, and result validation are enforced server-side.

The database stores Unix UTC instants; browser forms display the organizer's local
time. There is no timezone-aware recurring-event integration yet. The server rejects
cross-origin JSON changes and unknown Host headers. It does not log request payloads.

## HTTP interface

| Request | Purpose |
| --- | --- |
| `GET /api/sessions` | List local sessions |
| `POST /api/sessions` | Create a session |
| `GET /api/sessions/{id}` | Consistent session, roster, games, summary, recent audit snapshot |
| `POST /api/reclub/preview` | Read-only preview of a public Reclub meet link; no data is saved by preview alone |
| `POST /api/sessions/{id}/import` | Validate and import the engine's CSV format |
| `POST /api/sessions/{id}/import-reviewed` | Add selected reviewed players and partner preferences |
| `POST /api/sessions/{id}/demo` | Load synthetic players into an empty session |
| `POST /api/sessions/{id}/checkin-all` | Check in RSVP-yes players who are not already present |
| `POST /api/sessions/{id}/player` | Check-in, eligibility change, pause, resume, check-out |
| `POST /api/sessions/{id}/pair` | Add or remove a teammate preference |
| `POST /api/sessions/{id}/fill` | Fill available courts with valid balanced games |
| `POST /api/sessions/{id}/game` | Start, complete, cancel, swap a completed winner, or rebuild an unstarted game |
| `POST /api/sessions/{id}/reconcile` | Classify absent RSVP-yes players after the no-show cutoff |
| `POST /api/sessions/{id}/close` | End the rotation and finalize a rating period |

Session mutations require the current integer `revision`; creating a session does
not. Expected input problems return JSON errors; stale/invalid transitions return
409. On a playing court, **Team 1 Wins** / **Team 2 Wins** submits `winner: "a"`
or `winner: "b"`; no numeric score is requested or displayed. The existing score
columns store binary outcome indicators (1/0), not claimed point scores. The audit
identifies winner-only results. Existing API clients can still submit two unequal
integer scores from 0 to 99. Supplying scores and a winner together is rejected.
Both forms use the same guarded completion, queue return, correction, and rating logic.

## Edge cases and future policy

- Fewer than four eligible waiting players: leave the court empty with a reason.
- Impossible balance: no silent stacking or automatic relaxation; report the
  blocked oldest-player constraint. Multi-court look-ahead is not implemented.
- Player leaves mid-game: cancel with a reason, restore the queue, then check out
  the departing player. No result is fabricated.
- Medical or personal absence: record operational facts neutrally. Future sanctions
  need an explicit policy, exception handling, decay, and correction/audit process.
- Expired or unknown eligibility: a person may be present as a spectator, but not assigned.
- Closed session: read-only; corrections/reopening and rating replay are pending.
- Duplicate external accounts: do not merge by phone/email. An audited merge tool
  and guest-to-member conversion are pending.
- Event cancellation, court closure, payment changes, division restrictions, and
  missed notifications need verified upstream mappings and explicit operator policies.
- A no-show rate denominator must exclude valid cancellations and sync outages.
  Play-completion rate is completed assignments divided by assignments, not games
  played divided by check-ins, which can exceed one. Punctuality and reliability
  measures must be bounded and based on confirmed records before queue rewards.
- With 30 players and two doubles courts, only eight can play at a time. The
  remaining 22 necessarily wait. Average wait below three games is not guaranteed;
  define elapsed minutes, rounds, and games carefully before setting targets.
- Predicted imbalance outside 35–65% is distinct from actual lopsided score rate.
  Since assignments are gated at 40–60%, a zero predicted-imbalance rate alone
  cannot prove the system produces close games.

The MVP displays factual counts, queue order, skill bands, estimates, results,
and activity. It does not fabricate wait-time promises or claim the suggested
no-show, partner-repeat, utilization, or score targets have been achieved.

## Verification

Run the standard-library tests:

```sh
python3 -m unittest discover -s tests -v
```

They cover Glicko-2 numerics, stacking prevention, relationship costs, oldest-player
protection, arrival states, eligibility, import rollback/idempotency, capacity,
concurrent court fill, cancellation, duplicate results, period finalization,
persistence, and HTTP boundaries.

Optional browser smoke test requires an **already available** Node, Playwright
Core, and Chromium. It is a development check, not a runtime dependency. Start
the server against an isolated test database, then:

```sh
node tests/browser-smoke.cjs http://127.0.0.1:8080
```

Set `PICKLEQUEUE_PLAYWRIGHT_PATH` to an existing module path and `CHROMIUM_PATH`
to an existing executable if needed. `PICKLEQUEUE_SCREENSHOTS` selects an existing
screenshot directory. The smoke test creates a clearly marked synthetic session;
do not run it against your club's live records. No tooling is installed automatically.

See [docs/activity-log.md](docs/activity-log.md) for checks actually performed and
limitations. There is no claim of live Reclub, physical-device, Safari/Firefox,
hosted security, or production verification.

## Repository map

```text
picklequeue/
  engine.py      attendance, transactions, persistence, session lifecycle
  matching.py    candidate windows, team costs, oldest-player protection
  ratings.py     Glicko-2 core and documented doubles adaptation
  schema.sql     SQLite tables, constraints, and indexes
  server.py      loopback HTTP server and JSON boundary
web/
  index.html     public read-only Reclub attendee page for Vercel
  organizer.html local organizer UI and native dialogs
  attendees.js   same-origin attendee feed display
  styles.css     responsive layout, feedback, reduced-motion handling
  app.js         API interactions, navigation, forms, and polling cleanup
  favicon.svg
api/attendees.py read-only Vercel function for one configured event
examples/roster.csv
tests/test_engine.py
tests/browser-smoke.cjs
docs/activity-log.md
tools/                 repository safety, PR policy, and gated deployment checks
.github/               CODEOWNERS, CI, PR template, Vercel workflow
.githooks/             local commit/push guards
vercel.json            hosted config with automatic deployments disabled
AGENTS.md / CLAUDE.md   portable engineering and project instructions
CONTRIBUTING.md
SECURITY.md
LICENSE
```

## Next development steps

Keep the boundary simple: Reclub supplies event sign-ups, the organizer reviews
them and confirms physical attendance, the engine owns the queue, and completed
play supplies rating evidence. Next verify a supported Reclub contract and the
intended hosting/access model before connecting Vercel. Multi-organizer live sync,
manual match editing, advanced metrics, penalties, calendar inactivity, and rating
calibration remain separate increments.
