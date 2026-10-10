"""Reject private artifacts and recognizable credentials without printing values."""

import argparse
import re
import subprocess
from pathlib import PurePosixPath


PATTERNS = {
    'private key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----'),
    'GitHub token': re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})'),
    'AWS access key': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'Slack token': re.compile(rb'xox[baprs]-[A-Za-z0-9-]{20,}'),
    'Stripe secret': re.compile(rb'(?:sk|rk)_live_[A-Za-z0-9]{16,}'),
    'credential URL': re.compile(rb'[a-z][a-z0-9+.-]*://[^\s/:]+:[^\s/@]+@', re.I),
}


def forbidden_path(name):
    path = PurePosixPath(name)
    if any(part in {'data', '.vercel', '.venv', 'venv', 'node_modules', 'test-artifacts', '__pycache__'} for part in path.parts):
        return True
    basename = path.name.lower()
    return (
        basename == '.env' or basename.startswith('.env.') or basename.endswith('.env')
        or basename in {'id_rsa', 'id_ed25519', 'credentials.json', 'service-account.json'}
        or bool(re.search(r'\.(?:sqlite3?|db)(?:-.*)?$|\.(?:pem|key|p12|pfx|pyc|log)$', basename))
    )


def problems(name, body):
    found = ['private artifact'] if forbidden_path(name) else []
    found.extend(label for label, pattern in PATTERNS.items() if pattern.search(body))
    return found


def git(*args):
    return subprocess.check_output(['git', *args])


def scan(revision=None):
    if revision is None:
        names = git('ls-files', '-z').split(b'\0')
        read = lambda name: git('show', ':' + name)
    else:
        names = git('ls-tree', '-r', '--name-only', '-z', revision).split(b'\0')
        read = lambda name: git('show', revision + ':' + name)
    failures = []
    for raw in names:
        if not raw:
            continue
        name = raw.decode('utf-8', errors='surrogateescape')
        failures.extend((name, label) for label in problems(name, read(name)))
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', help='scan a committed tree instead of the index')
    parser.add_argument('--range', dest='commit_range', help='scan every committed tree in a revision range')
    parser.add_argument('--history', action='store_true', help='scan every tree in all reachable history')
    args = parser.parse_args()
    revisions = [args.revision]
    if args.history or args.commit_range:
        revisions = git('rev-list', '--all' if args.history else args.commit_range).decode().splitlines()
    failures = set()
    for revision in revisions:
        failures.update(scan(revision))
    for name, label in sorted(failures):
        print(f'REJECTED: {name!r}: {label}; remove the private artifact before committing.')
    if failures:
        return 1
    print('Repository safety check passed (paths and recognized credential patterns).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
