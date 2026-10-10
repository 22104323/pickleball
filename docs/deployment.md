# GitHub review and Vercel deployment

## Repository access and branch rules

The public release repository is `22104323/pickleball`, with `main` as its default
branch. The private development workspace is `22104323/pickleball-private`, with
`develop` as its default branch. `@22104323` is the only upstream writer in either
repository. Contributors can fork the public repository, push to their own fork, and
open a PR to public `main`; forks do not grant upstream write access. The public repo
is a personal repository, not an organization.

Both repositories have active rulesets with no bypass actors. Protected branches require
a PR, resolved review threads, and the GitHub Actions `verify` check. Required approval
count is zero because this is a one-maintainer project and GitHub prevents self-approval.
Force pushes and deletion are blocked. Development contribution checks are strict;
promotion checks are non-strict so a downstream promotion does not require rewriting
its upstream branch. Contributions squash; protected promotion branches merge to keep
shared history.

| Repository | Branch flow | Merge | Deployment |
| --- | --- | --- | --- |
| Private workspace | issue branch → `develop` → `staging` → `main` | Squash contributions; merge promotions | Staging/production workflow is preflight-gated |
| Public release | fork PR → `main`; maintainer release branch → `main` | Merge commit after `verify` | Blocked until hosted prerequisites are met |

The private ruleset protects `develop`, `staging`, and `main`. The public release ruleset
protects `main`; temporary release branches are deleted after merge. Public `develop`,
`staging`, and the earlier public feature branch are being retired after their history is
preserved in the private workspace. The initial release's temporary `release/#3` branch
was deleted after merge; the public repository now has only the long-lived `main` branch.

The public `staging` and `production` GitHub environments have owner approval gates for
their allowed branch. The private GitHub plan does not support required-reviewer
protection on private environments; no equivalent private approval gate is configured.
Deployment remains blocked by the repository's preflight until the hosted application
boundary is implemented, so the private staging workflow cannot deploy the local app.

Actions are SHA-pinned, restricted to GitHub-owned actions, read-only by default, and
cannot approve PRs. All external fork workflows need approval. Secret scanning, push
protection, private vulnerability reporting, Dependabot security updates, local hooks,
and private-artifact checks are enabled. Their scope does not prove complete secret
absence or enforce the currently unachieved 90% coverage target.

## Vercel deployment status

`vercel.json` disables automatic Git deployments so importing the project cannot bypass
the GitHub environment gate. `.github/workflows/deploy-vercel.yml` reruns tests and
requires hosted-route preflight before the deployment job can run. The REST client pins
the reviewed Git commit and waits for Vercel READY; queued or failed builds are not
reported as successful. No deployment dependencies or CLI packages are installed.

Preflight deliberately fails until a reviewed `api/attendees.py` and its website connection
exist. The current `web/app.js` uses the local organizer API, which must not be published
as an unauthenticated hosted API. Vercel cannot provide persistence for the local SQLite
file: its function filesystem is read-only apart from temporary scratch space.
[Vercel SQLite guidance](https://vercel.com/kb/guide/is-sqlite-supported-in-vercel)

The only Vercel deployment found is for the initial README-only commit, not the current
Courtside application. The private staging promotion's deployment workflow failed at
the hosted-route preflight, so the deployment job was skipped. No current app deployment
or verified Vercel project connection exists.

Before enabling deployment:

1. Implement/review the no-database Reclub website feed described below and its tests.
2. Connect the public release repository to a Vercel project, with project root at this repo and
   production branch `main`. Keep automatic deployments disabled in the committed config.
3. In each protected GitHub environment, store `VERCEL_TOKEN` as a secret; set
   `VERCEL_PROJECT_ID` and optional `VERCEL_TEAM_ID` as variables. Use a token scoped
   to the intended Vercel account/project access. Never put it in source or chat.
4. Confirm source privacy, displayed fields, build/runtime behavior, staging protection,
   and a live staging smoke test; then set `VERCEL_WEBSITE_READY=true` in that environment.
5. Approve promotion to staging; inspect its deployment and interactions before approving
   staging → main and the production deployment. Production release remains blocked
   until these prerequisites are complete.

Use Vercel's previous production deployment for a hosting rollback, then restore the
source through a reviewed revert PR. Do not force-push a protected branch or delete a
deployment needed for rollback. A hosting rollback does not undo upstream Reclub changes.

## Reclub compatibility check — 2026-10-10

Read-only checks used the supplied public sample event, without credentials. Real
names, IDs, avatar URLs, and raw responses were not saved to this repository or printed.

| Supplied endpoint | Result |
| --- | --- |
| `/meets/by-ref/E52MQB` | HTTP 200; 84 participant slots, 70 with status 1 |
| `/players/userIds?...&scopes=BASIC_PROFILE` | HTTP 200; two requested profiles returned with userId/name/imageUrl |
| `/groups/298257/activities?...` | HTTP 200; array of four activities in the sample time window |
| `/groups/slug/next11-pickleball-club?scopes=COUNTS` | HTTP 404 in this check |

The event response includes unique participant slot IDs, reference types, nullable
external references, status, and update times. No explicitly named attendance/check-in
field was found in participant objects. Treat status 1 as the supplied guide's sign-up
classification; the check does not independently establish every status/type semantic.
An anonymous HTTP 200 does not establish an integration SLA, unrestricted re-publication,
access to private events, or a supported developer contract.

Observed direct endpoint: [sample event API](https://api.reclub.co/meets/by-ref/E52MQB).
Official integration questions can go through [Reclub support](https://help.reclub.co/hc/reclub-help/articles/1765846581-how-do-i-report-an-issue-to-reclub).
No message was sent to Reclub.

## Proposed no-database attendee website

The website currently has a local same-browser session-link landing flow. **Generate Link**
creates a local `Open Play` session, stores a random UUID-to-session mapping in browser
`localStorage`, and puts the token in the URL fragment. The token is intentionally usable
only in that browser profile on that origin. It is not authentication, a secret access
control, cross-device sharing, or a hosted session record. Clearing browser storage loses
the mapping; local SQLite records persist on the organizer's computer. Do not expose the
local mutation API as a public service.

The user wants the website to reflect Reclub sign-ups without CSV or a duplicate member
database. A small Vercel serverless adapter can fetch one organizer-selected public event
by reference, then profiles in bounded batches. The browser reads only the website's
same-origin attendee endpoint. There is no Reclub write-back, organizer credential in
browser code, or stored roster. Short-lived memory caching/backoff can reduce upstream
load; they are caches, not a master user database. This adapter is **not yet implemented**.

- Select the owner's actual public event/club; the supplied Vietnam event is a compatibility
  sample, not a default production club. Do not expose an arbitrary upstream URL proxy.
- Output only an approved event title, sign-up status, participant-slot identifier, display
  name, and validated HTTPS avatar URL. Do not return raw event/profile responses, which
  contain unrelated fields including an access-token field.
- Preserve slot identity. A guest sharing the inviter's referenceId is a distinct slot;
  deduplicating solely by userId loses guests or displays the inviter twice. Use a neutral
  guest label when no name is supplied; do not fabricate a profile.
- Handle `externalReference: null`, missing names/profiles, cancellations, unsupported
  types/statuses, empty events, upstream changes, and partial responses explicitly.
- Use bounded requests, timeouts, profile batches, refresh limits, and 429 backoff. Show
  an upstream failure/stale warning; do not convert a fetch failure into zero attendees.
- Unix timestamps represent an instant independent of timezone. Build day boundaries
  using the club's actual timezone; do not apply the example's UTC+7 to a Manila club.
- One event of up to 50 own-account profiles ordinarily needs an event request and one
  batch-profile request. Event discovery and additional batches add requests. The pasted
  0.5-second estimate is not a service guarantee.
- Reject the old Nuxt HTML parser. Fix the pasted full-URL/base-URL duplication, list
  `.get()` call, nullable `.get()` call, and type-2 inviter/profile confusion.

Actual physical attendance, mutable court queues, and historical ratings remain separate
features. They cannot be inferred from public sign-ups. Their future persistence/access
design is not decided; do not deploy the local mutation API to make the preview appear live.
