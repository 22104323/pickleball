"""Prevent publishing a frontend whose hosted data route is not implemented."""

from pathlib import Path


def validate_website(root):
    root = Path(root)
    if not (root / 'api' / 'attendees.py').is_file():
        return 'The reviewed, read-only Reclub serverless adapter is not implemented. Deployment is blocked.'
    if '/api/attendees' not in (root / 'web' / 'app.js').read_text():
        return 'The website is not connected to the hosted attendee route. Deployment is blocked.'
    return None


def main():
    error = validate_website(Path(__file__).resolve().parent.parent)
    if error:
        print(error)
        return 1
    print('Hosted attendee route and frontend entry point are present; CI and maintainer review are still required.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
