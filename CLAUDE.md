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
- The user wants a Vercel website reflecting Reclub sign-ups without a second member
  database. The read-only hosted adapter and frontend connection are not implemented.
  No new stack or storage provider has been selected for a hosted queue engine.

## Commands

```sh
python3 -m picklequeue.server
python3 -m unittest discover -s tests -v
python3 -m compileall -q picklequeue tests tools
node --check web/app.js
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
- Contributions target `develop` and merge by squash. `develop` promotes to `staging`,
  then `staging` promotes to `main`, using reviewed merge commits to retain common
  ancestry for repeated promotions. This intentionally differs from Core's squash-only
  workflow, because an additional long-lived staging branch needs shared history.
- GitHub enforces one approval, code-owner approval when CODEOWNERS is on the base,
  stale-review dismissal, last-push approval, resolved threads, and the `verify` check.
- `develop` must be up to date. Promotion branches accept only the upstream protected
  branch and use merge commits; they do not require rewriting the upstream branch to
  include a downstream promotion commit. CI tests GitHub's proposed merge tree.
- No direct pushes, force pushes, branch deletion, bypass actors, or `--no-verify` on
  protected branches. GitHub enforces protection; local hooks are an additional guard.
- Explicit authorization is still needed for Git publication. Never merge just because
  checks pass. The sole current maintainer cannot approve a PR authored by the same account.
- Before opening a PR, settle issue reference, relevant screenshot states, omissions,
  review readiness, and any requested reviewers. Use `Refs` for incomplete work.

## Verification and deployment

- State step → verify before multi-step work. Preserve current behavior and user changes.
- New behavior gets meaningful tests. Run relevant existing checks and document limits
  in `docs/activity-log.md`. Browser inspection is distinct from reading source.
- Core's 90% line-coverage target remains a quality requirement. It is **not currently
  enforced or achieved** by this repo's CI; coverage instrumentation and browser CI
  remain pending. Never claim the existing unittest check proves that threshold.
- Both deployment environments require `@22104323` approval and disallow admin bypass.
  Staging deploys only from `staging`; production only from `main`.
- Vercel automatic Git deployments are disabled in `vercel.json`. Use the gated GitHub
  workflow, immutable commit SHA, environment-scoped token, and a checked READY state.
- Hosting currently fails preflight deliberately: the reviewed attendee endpoint and
  website connection are missing. A prepared workflow is not a deployed website.
- Reclub participant sign-up status must never be treated as physical check-in.
  No upstream write-back, scraping fallback, private endpoint guessing, or third-party
  personal data in fixtures, logs, screenshots, or committed artifacts.
- `.env`, databases, credentials, and `.vercel` metadata stay ignored. `.gitignore` and
  `.vercelignore` are public rules, not secret containers. Rotate an exposed credential;
  removing a file or adding an ignore rule does not undo disclosure.
