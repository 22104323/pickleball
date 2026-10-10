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
