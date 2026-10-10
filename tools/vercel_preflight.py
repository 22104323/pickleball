"""Verify that Vercel publishes only the read-only attendee website."""

from pathlib import Path


def validate_website(root):
    root = Path(root)
    if not (root / 'api' / 'attendees.py').is_file():
        return 'The read-only Reclub attendee route is missing. Deployment is blocked.'
    for name in ('web/index.html','web/attendees.js','.vercelignore'):
        if not (root / name).is_file():
            return f'The hosted attendee website file {name} is missing. Deployment is blocked.'
    page = (root / 'web' / 'index.html').read_text(encoding='utf-8')
    script = (root / 'web' / 'attendees.js').read_text(encoding='utf-8')
    ignored = (root / '.vercelignore').read_text(encoding='utf-8').splitlines()
    if '/attendees.js' not in page or 'app.js' in page:
        return 'The hosted page is not the read-only attendee website. Deployment is blocked.'
    if script.count('fetch(') != 1 or "fetch('/api/attendees'" not in script:
        return 'The attendee page is not connected to the hosted attendee route. Deployment is blocked.'
    if 'web/organizer.html' not in ignored or 'web/app.js' not in ignored:
        return 'The local organizer interface is not excluded from Vercel output. Deployment is blocked.'
    return None


def main():
    error = validate_website(Path(__file__).resolve().parent.parent)
    if error:
        print(error)
        return 1
    print('Read-only attendee route and hosted page are present; CI and maintainer review are still required.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
