# Activity log

## 2026-10-10 — Local pickleball queue MVP

- Sprint: unassigned. Issue: unassigned.
- Inspected the existing `22104323/pickleball` repository at
  `46af7c370b9d6e0cb5fb444450158e0f31b4a91c`; it contained only `README.md` and no
  implementation, dependencies, or project-specific agent instructions.
- Read the requested shared company policy and design guidance from
  `/home/pc-daryll/Documents/vault/second-brain/company/Agents/design`.
- The user asked to continue development while they sleep and defer instruction
  files. Implemented the local MVP and README without adding agent roles or
  instruction files, installing dependencies, or changing another repository.
- Built a loopback-only standard-library Python server, SQLite schema, responsive
  organizer interface, manual CSV roster adapter, attendance/eligibility gates,
  transactional balanced court fill, explicit starts/results, history costs,
  cancellation, session-close ratings, and audit records.
- Corrected the supplied Elo/Glicko-2 conflation, mixed team-sum/mean thresholds,
  contradictory partner-gap cap, and conflated RSVP/presence/queue states.
- Reclub's public site confirms product features, but no supported integration
  contract was verified. No live Reclub requests or upstream write-backs were made.
- Implemented the canonical Glicko-2 core and an explicitly experimental individual
  doubles observation model; rated sessions are frozen until close.
- Initial numerical test differed from the published rounded worked example by
  approximately 0.0093 rating point; comparison uses the published example's precision.
- Verification so far: 29 standard-library tests passed. Chromium smoke workflow
  passed session creation, check-ins, two balanced courts, result validation,
  cancellation, search, Back/Forward, reload, 390px mobile overflow, reduced motion,
  native-dialog keyboard focus, and rating finalization. Desktop (1440px) and mobile
  (390px) screenshots were inspected. The first browser harness attempt used a
  cached package with unresolved dependencies; using the existing Playwright Core
  package directly resolved it without installation. Browser assertions were updated
  to await completed view changes rather than inspect an in-flight response.
- Final checks are pending after mobile polish, cross-session history, and README changes.
- Remaining: real Reclub contract/credentials, hosted access controls/deployment,
  production data/physical-device/other-browser checks, doubles calibration, and
  future policy/features listed in README. No commit, push, or publication performed.

### Final verification

- `python3 -m unittest discover -s tests -v`: all 33 tests passed, including
  cross-session relationship history and prevention of overlapping rating periods.
- `python3 -m compileall -q picklequeue tests`: passed.
- Node syntax checks for `web/app.js` and `tests/browser-smoke.cjs`: passed using
  the installed Node 24.21.0 executable; no packages were installed.
- Browser smoke test passed against an isolated `/tmp` SQLite database, using the
  existing Playwright Core 1.59.1 cache and installed Chromium. It additionally
  verified CSV import, unknown eligibility, literal rendering of hostile HTML in
  names, mobile touch targets, and mobile session creation access.
- Synthetic simulation: 30 players, two courts, 40 completed games; each player
  played five or six games. No duplicate assignments, foreign-key failures, or
  SQLite integrity errors. This is a scenario result, not a universal wait-time guarantee.
- Desktop at 1440px and touch-emulated mobile at 390px were visually inspected;
  animations were allowed to finish before final screenshots. Reduced-motion
  content stays visible, native modal focus returns correctly, and repeated
  navigation/reload preserve session data.
- README local links, authored-file whitespace, and `git diff --check` passed.
  Runtime SQLite version was 3.53.4. Source and test databases remain separated.
- Live Reclub integration, hosted security/deployment, physical devices, other
  browsers, and predictive doubles calibration remain unverified/unimplemented
  as explicitly listed in README. Instruction files remain deferred.


## 2026-10-10 — Public repository, review rules, and deployment gates

- Sprint: unassigned. Issue: #1. The user explicitly requested GitHub hardening,
  publication, open-source visibility, staging/production, Vercel hosting, and a
  pull request ready for review. Named maintainer: @22104323. No new collaborator,
  organization transfer, sub-agent, runtime dependency, or schema change was made.
- Read the requested shared policy and Core CLAUDE rules; added portable engineering
  guidance and actual project commands. Preserved the Python/SQLite/plain-web stack.
  The other developer's Next.js/Express/Socket.io/Prisma stack is a reference, not
  an approved migration. The local organizer remains separate from future hosting.
- Changed repository visibility from private to public after inspecting its initial
  history (README only). Created develop and staging from that seed, set develop
  as default, and installed active rulesets 24824359 and 24824739 with no bypass
  actors. Required reviews/checks, code ownership, resolved threads, stale/last-push
  review rules, no deletion, and no force pushes are enforced by GitHub.
- Contributions squash into develop; staging/production promotions use merge commits
  to preserve ancestry across repeated releases. Promotion checks are non-strict;
  develop remains strict. This deliberate adaptation differs from Core's squash-only
  policy and is documented in the project's instructions and deployment guide.
- Staging/production environment branches are restricted and require @22104323
  approval, with admin bypass disabled. Self-approval of a deployment is allowed;
  self-approval of a PR is not. The bootstrap PR needs a different trusted reviewer.
- Enabled secret scanning, push protection, private vulnerability reporting,
  Dependabot security updates, SHA-pinned GitHub-owned Actions only, read-only tokens,
  no workflow PR approval, and maintainer approval for all external fork workflows.
- Added ignored private artifacts, commit/push guards, history checks, PR naming and
  promotion checks, tests, CI, Vercel REST deployment tooling, and hosting preflight.
  The deployment gate correctly fails until the read-only attendee API and its website
  connection exist; this is not a live Vercel deployment. No Vercel login/token/browser
  connection exists in this workspace. Tokens remain environment secrets, not files.
- MIT is the recommended permissive open-source license, selected for this initial
  publication; it does not give contributors repository write or merge permissions.
- User prefers Reclub-sourced attendees without CSV or a second member database.
  Checked the supplied public endpoints read-only, without credentials. Meet E52MQB
  returned HTTP 200 with 84 slots, 70 status-1 records, and distinct slot IDs;
  two-profile batch returned HTTP 200 with the expected name/avatar fields;
  the group activities endpoint returned HTTP 200; supplied slug lookup returned 404.
  Stored only schema/count observations, not raw responses or personal records.
- Found no explicitly named check-in/attendance field in participant records.
  Sign-up status is not evidence of physical attendance. Documented nullable external
  references, guest/inviter confusion, removed Nuxt scraping, timestamp semantics,
  response filtering (including an upstream access-token field), and bounded fetches.
  Integration support/SLA, private-event behavior, and the owner's actual club/event
  remain unverified. No Reclub message, write-back, or live website sync was performed.
- Verification: 47 unittest tests passed, compileall passed, Node syntax checks passed,
  git whitespace passed before staging, hooks configured, and ignore checks confirmed
  root/nested .env, SQLite data, and Vercel metadata are excluded while .gitignore is
  tracked. GitHub settings were read back successfully. Desktop/mobile synthetic
  screenshots from the earlier browser smoke test were inspected again for PR review.
- Diagnostic stdlib trace of the original 33-test suite: engine 87.8%, matching 100%,
  ratings 87.5%, server 48.8%. The 90% target is not achieved/enforced; browser CI and
  coverage instrumentation remain unfinished. Do not equate passing unit CI with them.
- Commit/push, remote CI, final rule readback, and PR URL verification follow below.


### Publication verification

- Published commit `85776fe2bb8c3f4bedb70096eba4ae11f1730691` to `feature/#1`.
  Created ready-for-review PR #2 targeting develop; issue #1 remains open because
  hosting/integration is incomplete. Git uses the owner's GitHub no-reply address
  for new commits; the global Git configuration and seed history were not changed.
- GitHub push CI run 38012342571 and PR CI run 38012391098 both passed; the required
  `verify` check is supplied by GitHub Actions app 15368, matching the rulesets.
  PR state was OPEN, not draft, MERGEABLE, BLOCKED, with REVIEW_REQUIRED.
- Remote branch SHAs were verified. Main, develop, and staging remain at the original
  seed; all published project changes are on the feature branch awaiting review.
  No protected-branch push, bypass, merge, force operation, or deployment occurred.
- Negative checks passed for local main/develop/staging pushes, invalid contribution
  branch names, and an explicitly staged synthetic .env in an isolated temporary repo.
  Top-level Markdown links and the committed history safety scan passed. `.gitignore`
  stays tracked while private files remain excluded. Only @22104323 has repository access.
- The installed gh version does not support `pr checks --json`; PR/check-runs APIs
  provided the successful check state instead. No workflow failure was hidden.
- A second trusted maintainer/code owner is needed for an enduring two-person review
  workflow. The owner cannot approve PRs or last pushes attributed to the same account.
  No additional person was invited without a supplied username and authorized scope.
- Current Vercel guidance (June 2026 beta) supports WebSockets, including Socket.io;
  connections are instance-bound/duration-limited and shared realtime state needs a
  cross-instance design. This does not make Reclub push events available. The referenced
  Next.js/Postgres/Prisma/Tailwind/Zustand stack has not been adopted or installed.


## 2026-10-10 — Dropdown styling

- Polished the existing native dropdown controls with a consistent Courtside chevron,
  responsive hover/focus/disabled styling, and compact spacing for attendance fields.
  Kept native select behavior for keyboard access and platform picker support. The
  referenced skill-level dropdown is not present in the current interface.
- Verification: source diff reviewed and whitespace check passed. No browser inspection
  or automated tests were run for this CSS-only update.


## 2026-10-10 — Courtside roster, modes, and result corrections

- Integrated the earlier local work for optional Guide me, eight play formats,
  pasted/public-Reclub roster review, bulk skill priors, pairing/unpairing, and
  organizer check-in-all. SQLite version 2 retains version-1 data; its migration
  is covered by the existing regression test. Reclub remains read-only and RSVPs
  remain absent until organizer check-in. No new runtime dependencies or stack change.
- Implemented inline Swap winner / Cancel / Swap for completed games in active
  sessions. Exchanges scores and audits before/after values without changing game
  identity, court, completion time, count, games played, queue tickets, or staged teams.
  Closed sessions stay read-only; corrected results are rated once at session close.
- Added result-derived Live Standings and a local display view. Explicit Rebuild
  reuses mode-aware selection, preserves other courts and original queue priority,
  and atomically keeps the old plan when no alternative exists. Corrected recent
  outcome labels can change independently of the reserved teams.
- Preserved rating priors on reviewed reimport and rejected pair/category/group
  changes affecting active games. Mixed Doubles handles unset categories as an
  invalid pool instead of a comparison error. These checks keep review imports
  from bypassing the existing pairing and game rules.
- Reused shared CSS motion settings for 700ms/28px/80ms initial reveals, 260ms
  incoming views and guide text, restrained button feedback, and desktop-only
  elastic format cards. IntersectionObserver reveals once; reduced motion and
  missing-observer fallback show content immediately. No added decorative assets.
- Verification: 67 unittest tests passed; compileall and Node 24.21.0 syntax checks
  passed. Expanded Playwright Core / Chromium smoke passed desktop, 390px mobile
  touch targets, Back/Forward, reload, optional guide, score validation, inline
  cancellation/correction, standings, preserved staged games, Rebuild, local display,
  reduced motion, missing IntersectionObserver, keyboard dialog focus, rating close,
  unknown eligibility, and HTML escaping. Used an isolated temporary SQLite database.
- REA Chromium 150.0.7871.124 desktop evidence:
  `ev_affd32038f6fb5037b6f7d7d41af30610472fbf33785b425fa3007c43cf3a991`.
  Confirmed Cancel and corrected standings after three synthetic games; all four
  games-played values remained 3. Mobile viewport/reduced-motion Winners / Losers:
  `ev_7a0a06c570db50f70437929b4ee1d02dfc4688f7ad72ecbf9e4e9c979c407ce2`.
  Staged teams stayed fixed after swap; explicit Rebuild used corrected outcome groups.
  Both completed without page-error events; owned browser processes were terminated.
- Failed exploratory REA run `ev_55131d32e397f52c007ffcde8188e841067fc7c8a96035d89419d3fa4eb59a43`
  used a non-unique wait selector; subsequent actions were cancelled. Corrected it
  before the successful desktop run. One smoke rerun read attendance before the
  request completed; replaced that check with a wait for visible present status,
  then the suite passed. Repeating the test on that same synthetic database later
  correctly blocked its reused member identity from joining a second active session.
  Added a unique synthetic external ID and used a fresh database for the final run.
  No failed step is treated as positive evidence.
- Read GitHub back: active rulesets 24824359 and 24824739 protect develop/staging/main,
  one approval, code-owner review when CODEOWNERS exists on the base, last-push approval,
  resolved threads, verify, force/deletion blocks, and no bypass actors. Secret scanning,
  push protection, and owner-approved staging/production environments remain enabled.
  Feature PR #2 still needs an independent reviewer; no protected branch was changed.
- Remaining: Vercel connection/hosted Reclub adapter, club/cloud/multi-device behavior,
  Safari/Firefox/physical-device verification, automated browser CI, and the 90% coverage
  target are unfinished. Dynamic court management, manual team editing, and independent
  future-match slots beyond one reservation per free court remain separate increments.


## 2026-10-10 — Skills-only UI and reference winner controls (#1, sprint unassigned)

- Applied the local design repository's engineering rules, design filter, and motion
  specification to the existing Courtside interface. Kept the current stack, brand
  palette, navigation, attendance gates, queue selection, and lightweight motion.
  No additional design prompt or dependency was needed.
- Corrected the earlier mismatch with the supplied screenshots: playing courts now
  expose Team 1 Wins and Team 2 Wins directly. Removed the numeric result dialog and
  score column. Completion accepts an explicit winner, records binary outcome markers
  in existing columns, and audits winner-only results without inventing point scores.
  Legacy score submissions remain compatible; mixed winner/score payloads are rejected.
  Corrections, standings, rating finalization, and explicit Rebuild use the same engine.
- Removed gender controls and gender submission from player review. Individual star
  skills and the bulk selector show current/mixed levels, retaining pairing/unpairing.
  Mixed Doubles is visibly disabled for skills-only setup rather than offering a format
  that requires unavailable category inputs. Existing stored categories are untouched.
- Enhanced native dropdowns progressively with styled pickers where supported; retained
  native browser fallback, keyboard selection, Escape, and focus indicators. Improved
  form targets, readable supporting text, panel consistency, paired badges, team
  grouping, and mobile attendance cards. Review rerenders preserve keyboard focus and
  list scroll. Fixed a mobile review-footer clipping problem found during visual QA.
- Verification: 68 unittest tests passed, including invalid winner/mixed payload rollback,
  duplicate completion, winner-only counts, audit, and correction. Existing legacy-score
  tests continue to pass. Compileall, Node 24 syntax checks, and whitespace checks passed.
  Expanded Chromium 150.0.7871.124 smoke passed desktop/mobile/touch, Back/Forward, reload,
  winner buttons, correction/Cancel, standings, reserved teams, Rebuild, rating close,
  reduced motion, missing IntersectionObserver, skills, checkbox keyboard focus,
  unknown eligibility, and HTML escaping. Additional fresh browser-context inspection
  exercised bulk/individual levels, pairing, native picker/Escape, mobile review and
  attendance, eligibility, and Team 2 Wins; no page errors or body overflow occurred.
  All sessions and screenshots used synthetic names and temporary SQLite databases.
- Initial added unit test treated serialized audit detail as a dict; corrected the
  assertion to parse JSON before the passing run. An exploratory browser check targeted
  Save instead of its accessible Save eligibility name and timed out; corrected the
  locator before the successful run. Neither failed check is counted as passing.
- Read GitHub rulesets back: develop and staging/main protections remain active with
  one approval, last-push/code-owner review, resolved threads, verify, deletion/force
  blocks, and no bypass actors. No protection, deployment, schema, or permission change.
- Not verified: Safari, Firefox, physical devices, screen readers, club/cloud sharing,
  hosted Reclub, and Vercel deployment. Existing hosted integration and independent
  future-match/court-management work remains pending.


## 2026-10-10 — Reference court, queue, and Up Next layout (#1, sprint unassigned)

- Corrected the structural mismatch with the supplied PickleQ screenshot: replaced
  the permanent sidebar and large metric cards with a compact session header/menu,
  placed Live Courts above the rotation, and put an ordered Queue beside separate
  numbered Up Next cards. Retained Courtside's palette, typography, native enhanced
  dropdowns, skills-only review, attendance gates, and explicit winner buttons.
- Queue rows now include waiting and reserved players until their game starts;
  reservations are labelled and cannot be paused without resolving their match.
  The header's occupied-court count includes playing games only. Court previews
  expose Start Up Next; the matching card exposes Send to Court, Rebuild, and Cancel,
  using existing actions. Outcome group badges require every player to share a known
  outcome. No engine, schema, dependency, hosting, or GitHub permission change.
- Menu navigation retains browser history and keyboard focus; Escape closes the menu
  and restores its trigger. Header counters remain stable during content transitions.
  Mobile stacks Up Next before the queue, with existing reduced-motion behavior.
- Verification: 68 existing unittest tests passed. Expanded Chromium 150.0.7871.124
  browser smoke passed desktop/mobile, menu Escape, queue/card geometry, counts,
  winner buttons, correction/Cancel, standings, reserved teams, Rebuild, Back/Forward,
  reload, reduced motion, missing IntersectionObserver, review skills, dialog focus,
  unknown eligibility, and HTML escaping. Additional fresh-context checks covered
  bulk/individual skills, pairing, enhanced picker/Escape, mobile review/attendance,
  eligibility, and Team 2 Wins. No page errors or body overflow in successful runs.
- A separate fresh one-court, nine-player Winners / Losers scenario used equal-skill
  synthetic CSV fixtures through the existing local API, then organizer UI check-ins,
  starts, and three winner-button results. Verified desktop geometry, mobile width,
  four changed win totals after correction, unchanged games-played counts, completed
  match count, and the full staged game. Saved fresh reference and winner screenshots.
  These checks establish local browser behavior only, not club/cloud behavior.
- Initial menu test timed out because its accessible name included the queue count;
  marked the decorative count aria-hidden and reran successfully. The exploratory
  varied-rating demo could not form a valid later Winners / Losers game; retained its
  balance constraints and used equal-skill fixtures for the controlled scenario.
  Two fixture retries read the URL before navigation completed; another asserted
  queue rows before view rendering. Added explicit navigation/render waits before
  the successful scenario. Failed steps are not treated as positive evidence.
- Manual team editing, player-call controls, adding/removing courts, and independent
  future-match slots remain pending; Up Next still reserves one game per free court.
  Not verified: Safari/Firefox, physical devices, screen readers, cloud sharing,
  hosted Reclub, Vercel deployment, browser CI, or the 90% coverage target.
- Compileall, Node 24 syntax, whitespace, staged repository, and history safety checks
  passed. Read back both active GitHub rulesets: review/check requirements, force/deletion
  blocks, and empty bypass actor lists remain in effect for develop, staging, and main.


## 2026-10-10 — Left navigation and direct skill stars (#1, sprint unassigned)

- Removed the header hamburger dropdown and placed the five session destinations as
  navigation buttons on the left side of the desktop workspace. Tablet layouts use a
  horizontal button rail; mobile uses a compact five-button row. The session selector,
  header counts, route history, and selected-page state remain in place.
- Replaced each player's skill dropdown with six directly clickable, accessible star
  choices. A click sets the matching skill immediately; arrow/Home/End keys move among
  radio choices. A per-player Clear button preserves the old ability to unset one rating.
  The bulk selected-player level dropdown remains.
- Updated the existing browser smoke script for the new navigation and star control.
  Tests were not run for this change. Fresh browser screenshots were not captured.


## 2026-10-10 — Same-browser session links and one-maintainer release path (#3, sprint unassigned)

- Added the requested minimal COURTSIDE landing screen with a Generate Link button.
  Generating it creates a local Open Play session, gives it a random UUID token in the
  URL fragment, and stores the token-to-local-session mapping in this browser's local
  storage. It then opens the existing organizer dashboard. Unknown tokens remain on
  the landing screen with a clear same-browser message. Numeric session IDs are not
  accepted as link credentials. The token is not authentication or cross-device access;
  session records still live in the local SQLite database.
- Matched the supplied landing screenshot's centered title, compact outlined button,
  white background, and top spacing. Added a small self-hosted Patrick Hand font under
  its included SIL OFL license, with no third-party runtime request. The local server
  exposes only that specific font path. Updated browser smoke coverage for fresh landing,
  generated link, reload, and isolated browser storage.
- Updated contribution and deployment documentation for a one-person release process:
  PR plus `verify` checks remain required, approval count is zero, no bypass actors,
  force pushes, or protected-branch deletion. The private workspace keeps development
  and staging; contributors fork the public repo and open PRs to main. Public legacy
  development refs are pending retirement after the release is ready.
- Verification: all 69 Python tests passed; repository path/credential checks passed.
  Temporary SQLite and Chrome 150.0.7871.124 profiles confirmed the landing screen,
  UUID link creation, dashboard transition, same-profile reload, and rejection of the
  same URL from an isolated profile with no local mapping. Desktop/mobile landing and
  dashboard captures are in `docs/screenshots/`. The browser smoke script was updated
  but not run locally; Node is unavailable. GitHub CI runs Node syntax checks, but it
  does not execute the Playwright browser smoke.
- Early exploratory CDP attempts had harness issues with Chromium's handshake wording,
  navigating targets, and WebSocket frames. The harness was corrected and rerun using
  fresh targets and isolated temporary profiles. No product failure was observed.
- The first GitHub `verify` run caught trailing whitespace carried by the upstream OFL
  text file. Removed whitespace only; the included license wording is unchanged, then
  reran repository checks before pushing the correction.
- No hosted app deployment was performed. The current Vercel preflight still blocks
  until the hosted Reclub attendee route exists; the local SQLite API is not deployed.


## 2026-10-10 — Public source release complete (#3, sprint unassigned)

- Merged public PR #4 to protected `main` using the ruleset's required merge commit.
  Public main now contains the Courtside app and the same-browser Generate Link flow.
  The temporary `release/#3` branch was deleted automatically. Public PR #2 was closed;
  old public `develop`, `staging`, and `feature/#1` refs were removed after preserving
  the work in the private development workspace. The public repository now has only
  `main` as a branch. Contributors can fork and submit PRs; only `@22104323` has upstream
  write access.
- A GitHub readback found both repositories private, contrary to the open-source request.
  Restored `22104323/pickleball` to public while keeping the development workspace private.
  Read back the active public ruleset: only `main` is targeted; PR and `verify` required;
  approval count zero; no bypass actors; force push and branch deletion blocked.
- Public PR #4's `verify` checks passed, and the post-merge CI workflow passed. The
  post-merge Vercel workflow failed at the expected hosted-data-boundary preflight and
  skipped deployment because the reviewed Reclub attendee route is not implemented.
  This is a GitHub source release, not a deployed website.
- Corrected the deployment guide's public merge-method statement to match the active
  merge-only ruleset and recorded the final branch/deployment status in this entry.
