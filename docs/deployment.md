# GitHub review and Vercel deployment

> Current product: full green Courtside UI, browser execution, no accounts, no paid
> backend, no server roster storage, and 48-hour snapshot links. See
> [browser sessions](browser-sessions.md). The attendee-only feed sections below
> record the earlier implementation and are superseded by that guide.

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
`staging`, and `feature/#1` were removed after their history was preserved in the private
workspace. The initial release's temporary `release/#3` branch was deleted after merge,
and superseded public PR #2 was closed. The public repository now has only the long-lived
`main` branch.

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

The current hosted source is the full browser organizer at `web/index.html`.
Preflight verifies browser runtime wiring and excludes `api/` and the local-only
`web/organizer.html`. The browser fetches Reclub directly and saves queue state on
the device; no Python function or hosted SQLite database is required. See
[browser session behavior](browser-sessions.md) and
[`.vercelignore` documentation](https://vercel.com/docs/deployments/vercel-ignore).

On 2026-10-10 the public URL `https://pickleball-beige-xi.vercel.app/` returned
HTTP 200 with the previous attendee-only entry page. That deployment exists, but
the corrected browser organizer is not yet deployed. The production GitHub
environment has no configured deployment secret/variables in the latest check,
and no local Vercel credentials/project metadata are available to this agent.

Before enabling deployment:

1. Review the browser organizer, snapshot sharing, expiry limitations, and direct
   public Reclub import described in [browser sessions](browser-sessions.md). No
   event or club is selected by deployment configuration.
2. Connect the public release repository to a Vercel project, with project root at this repo and
   production branch `main`. Keep automatic deployments disabled in the committed config.
3. In each protected GitHub environment, store `VERCEL_TOKEN` as a secret; set
   `VERCEL_PROJECT_ID` and optional `VERCEL_TEAM_ID` as variables. Use a token scoped
   to the intended Vercel account/project access. Never put it in source or chat.
4. Review the browser session behavior, direct Reclub imports, build/runtime behavior,
   and staging protection. Set `VERCEL_WEBSITE_READY=true` in the protected GitHub
   staging environment to allow deployment. No `RECLUB_EVENT_REF` is required.
5. Approve the staging deployment and run its live smoke test. After it passes, set
   `VERCEL_WEBSITE_READY=true` in the protected GitHub production environment. Approve
   staging → main and the production deployment separately.

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

## Previous attendee-only implementation (superseded)

The local organizer interface has a same-browser session-link landing flow. **Generate
Link** creates a local `Open Play` session, stores a random UUID-to-session mapping in browser
`localStorage`, and puts the token in the URL fragment. The token is intentionally usable
only in that browser profile on that origin. It is not authentication, a secret access
control, cross-device sharing, or a hosted session record. Clearing browser storage loses
the mapping; local SQLite records persist on the organizer's computer. Do not expose the
local mutation API as a public service.

The hosted website reflects one Reclub event without CSV or a duplicate member database.
`RECLUB_EVENT_REF` selects the event at deploy configuration; requests cannot select an
event or provide an upstream URL, and the HTTP client rejects upstream redirects. The
Python route fetches the event and account profiles in bounded batches. The browser reads
only the same-origin attendee endpoint. The route has no SQLite access, write method,
Reclub credential, or stored roster. Vercel CDN
caching is short-lived response caching, not a master user database. The code is
implemented, but no event is configured and no live deployment or privacy approval has
been completed.

- Select the owner's actual public event/club; the supplied Vietnam event is a compatibility
  sample, not a default production club. Do not expose an arbitrary upstream URL proxy.
- Output only an event title, status 1, participant-slot ID, display name, and a validated
  HTTPS avatar URL from `assets.reclub.co` or `d1upr18ac2olqz.cloudfront.net`. Invalid,
  credential-bearing, query-string, or non-HTTPS image URLs are omitted. The response
  also includes a fetch timestamp and static warnings. Do not return raw event/profile
  responses, which contain unrelated fields including an access-token field.
- Preserve slot identity. A guest sharing the inviter's referenceId is a distinct slot;
  deduplicating solely by userId loses guests or displays the inviter twice. Use a neutral
  guest label when no name is supplied; do not fabricate a profile. When an upstream slot
  ID is missing, return a derived opaque identifier rather than a user ID.
- Handle `externalReference: null`, missing names/profiles, cancellations, unsupported
  types/statuses, empty events, upstream changes, and partial responses explicitly.
- Bound event responses to 2 MB, raw event slots to 1,000, displayed sign-ups to 200,
  profile batches to 50, and each HTTP attempt to five seconds. Retry an upstream 429
  at most once per request, with a maximum one-second wait. The function has a 45-second
  runtime budget for the bounded five-request worst case. The browser refresh button has a
  60-second cooldown; successful responses use a 60-second CDN cache with stale-while-
  revalidate and stale-if-error windows. A fetch timestamp lets the page identify old
  cached data. An in-page failure keeps the last successful list with a warning; an
  initial failure shows no attendee count. A valid empty response is shown as zero.
  The CDN cache reduces upstream requests but is not a strict per-client rate limit.
- One event of up to 50 own-account profiles ordinarily needs an event request and one
  batch-profile request. Additional profiles use more batches, up to 200 displayed
  sign-ups. Event discovery is not implemented. The pasted 0.5-second estimate is not a
  service guarantee.
- The implementation uses fixed JSON API paths and does not use the pasted Nuxt HTML
  parser or caller-supplied upstream URLs.

Actual physical attendance, mutable court queues, and historical ratings remain separate
features. They cannot be inferred from public sign-ups. Their future persistence/access
design is not decided; do not deploy the local mutation API to make the preview appear live.
