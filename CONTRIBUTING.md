# Contributing

Open an issue before starting a change. If you do not have write access, fork the repo
and push your branch there. Public visibility does not grant write access to this repo.
Only invite trusted maintainers; contributors can use fork pull requests without an invitation.

Use `feature/#<issue-number>`, `bugfix/#<issue-number>`, `hotfix/#<issue-number>`,
`release/#<issue-number>`, or `docs/#<issue-number>`. Target `develop`.
Commit and PR titles use `feat(#1): [Browser] describe the actual change` or the relevant
Conventional Commit type and real issue number. Include purpose, test results, omissions,
and screenshots for visible website changes. Do not add generated-by or co-author footers.

Enable local guards once per clone:

```sh
git config core.hooksPath .githooks
python3 -m unittest discover -s tests -v
node --check web/app.js
python3 tools/check_repository.py --history
```

All contribution workflows use a read-only GitHub token and no deployment secrets.
External fork workflows require maintainer approval. Actions are pinned to full commit
SHAs and restricted to GitHub-owned actions. CI, passing reviews, and code-owner approval
are required to merge; changes after approval require a new review. Maintainers promote
`develop → staging → main` through reviewed PRs. Squash contributions into develop;
use merge commits for promotions so repeated releases retain a shared ancestor.

The current account is a personal GitHub repository, with organization-style review
controls. No organization transfer or extra collaborator access was performed.
`@22104323` owns code review. GitHub disallows self-approval, so maintainer-authored
PRs need another trusted reviewer; the initial bootstrap PR remains unmerged until then.

Never commit `.env`, tokens, credentials, databases, roster exports, or real personal
data. Track `.gitignore` and `.vercelignore` so everyone shares the exclusion rules.
Use synthetic data for tests/screenshots. See [SECURITY.md](SECURITY.md) for private reports
and [docs/deployment.md](docs/deployment.md) for the gated deployment flow.
