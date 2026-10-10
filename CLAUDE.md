# Courtside project instructions

Read README and the portable [shared engineering policy](docs/engineering-policy.md).
This file incorporates the applicable review, Git, verification, and security rules
from the owner's Core policy. Core's Nuxt/pnpm, mobile apps, Postgres migrations,
deployment hosts, project board, and identifier conventions are not this project's stack.

## Stack and structure

- Python 3.11+ standard library and SQLite 3.35+ in `picklequeue/`; no runtime packages.
- Plain HTML/CSS/JavaScript in `web/`; no build step for local use.
- Python unittest and an optional Playwright Core/Chromium smoke test in `tests/`.
- Repository/deployment checks in `tools/`; CI in `.github/workflows/`; hooks in `.githooks/`.
- The current organizer server is loopback-only. Never expose its unauthenticated
  mutation routes on Vercel or another public host.
- The local organizer includes read-only Reclub preview. The hosted organizer uses
  the original green UI with a browser JavaScript queue, 48-hour isolated sessions,
  copied snapshot links, and direct public Reclub imports. No hosted database,
  account, or paid backend is used. Shared live editing is not implemented.
  See [browser session behavior](docs/browser-sessions.md).

## Commands

```sh
python3 -m picklequeue.server
python3 -m unittest discover -s tests -v
python3 -m compileall -q picklequeue tests tools
node --check web/app.js
node --check web/browser-engine.js
node --check tests/browser-smoke.cjs
python3 tools/check_repository.py --history
git diff --check
git config core.hooksPath .githooks
git config core.hooksPath
```

Node 24 is the CI tooling runtime; it is not required to serve the local website.
The optional browser command and prerequisites are in README. Never install missing
packages automatically. New dependencies, schema/auth changes, and major boundaries
need a concrete approved scope; do not assume another project's provider choices.

## Git and review

- Start with a real issue. Sprint is `unassigned` until the user assigns one.
- Contribution branches: `feature/#<issue-number>`, `bugfix/#<issue-number>`,
  `hotfix/#<issue-number>`, `release/#<issue-number>`, or `docs/#<issue-number>`.
- Commits and PR titles use Conventional Commits with the actual issue in the scope.
  Website changes use `[Browser]` after the prefix. No co-author or generated-by footers.
- The public repository keeps releases on `main`; contributors fork it and open PRs to
  `main`. A temporary maintainer `release/#<issue>` branch is used for owner-authored
  releases. The separate private workspace uses `feature/#<issue> → develop → staging
  → main` PRs, with squash for contributions and merge commits for promotions.
- Both repositories require PRs and the `verify` status check on protected branches.
  The one-person process has no required approval because the sole maintainer cannot
  independently review their own PR. `@22104323` may merge once the required CI passes.
- In the private workspace, `develop` promotes only to `staging`, then `staging` to
  `main`; merge commits preserve ancestry. Public `main` accepts issue-linked fork PRs
  and owner-authored temporary release PRs only.
- No direct protected-branch pushes, force pushes, branch deletion, bypass actors, or
  `--no-verify`. GitHub rulesets enforce the policy; local hooks provide another guard.
- Git publication still needs explicit user authorization for the scope of a release.
  Passing checks alone do not authorize unrelated changes or a deployment.
- Before opening a PR, settle issue reference, relevant screenshot states, omissions,
  review readiness, and any requested reviewers. Use `Refs` for incomplete work.

## Verification and deployment

- State step → verify before multi-step work. Preserve current behavior and user changes.
- New behavior gets meaningful tests. Run relevant existing checks and document limits
  in `docs/activity-log.md`. Browser inspection is distinct from reading source.
- Core's 90% line-coverage target remains a quality requirement. It is **not currently
  enforced or achieved** by this repo's CI; coverage instrumentation and browser CI
  remain pending. Never claim the existing unittest check proves that threshold.
- Public staging and production GitHub environments require `@22104323` approval and
  disallow deployment bypass. The private GitHub plan does not offer required reviewers
  for private environments; configure the protected deployment settings before deployment.
  Staging deploys only from `staging`; production only from `main`.
- Vercel automatic Git deployments are disabled in `vercel.json`. Use the gated GitHub
  workflow, immutable commit SHA, environment-scoped token, and a checked READY state.
- Hosted preflight checks browser runtime wiring and server-route exclusions. A passing
  preflight is not a live deployment; inspect READY and the actual deployed commit.
- Reclub participant sign-up status must never be treated as physical check-in.
  No upstream write-back, scraping fallback, private endpoint guessing, or third-party
  personal data in fixtures, logs, screenshots, or committed artifacts.
- `.env`, databases, credentials, and `.vercel` metadata stay ignored. `.gitignore` and
  `.vercelignore` are public rules, not secret containers. Rotate an exposed credential;
  removing a file or adding an ignore rule does not undo disclosure.
