# Contributing

Open an issue before starting a change. Public visibility does not grant write access
to this repository. Contributors can fork it, push to their own fork, and open a PR to
`main`. Do not request upstream write access for a contribution.

Use `feature/#<issue-number>`, `bugfix/#<issue-number>`, `hotfix/#<issue-number>`,
`release/#<issue-number>`, or `docs/#<issue-number>`. Fork contributions target `main`.
Maintainer releases use a temporary `release/#<issue-number>` branch and a PR to `main`.
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
SHAs and restricted to GitHub-owned actions. A PR and passing `verify` checks are required
to merge. The repository has one maintainer, so the rules do not require an independent
approval; `@22104323` checks and merges after CI passes. Direct pushes to `main`, force
pushes, deletion, and bypass are blocked. Development and staging promotion PRs live in
the separate private workspace; the public repository carries releases on `main`.

The public project remains a personal repository, not an organization. Only `@22104323`
has upstream write access. Forks let contributors push their own branches without
granting access to the release repository.

Never commit `.env`, tokens, credentials, databases, roster exports, or real personal
data. Track `.gitignore` and `.vercelignore` so everyone shares the exclusion rules.
Use synthetic data for tests/screenshots. See [SECURITY.md](SECURITY.md) for private reports
and [docs/deployment.md](docs/deployment.md) for the gated deployment flow.
