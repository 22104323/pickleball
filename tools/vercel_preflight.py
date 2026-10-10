"""Verify that Vercel publishes the browser queue without organizer server routes."""

from pathlib import Path


def validate_website(root):
    root = Path(root)
    for name in ('web/index.html','web/app.js','web/browser-engine.js','.vercelignore'):
        if not (root / name).is_file():
            return f'The browser queue file {name} is missing. Deployment is blocked.'
    page = (root / 'web' / 'index.html').read_text(encoding='utf-8')
    script = (root / 'web' / 'browser-engine.js').read_text(encoding='utf-8')
    ignored = (root / '.vercelignore').read_text(encoding='utf-8').splitlines()
    if ('data-runtime="browser"' not in page or '/browser-engine.js' not in page
            or '/app.js' not in page or '/attendees.js' in page
            or page.index('/browser-engine.js') > page.index('/app.js')):
        return 'The hosted organizer is not connected to its browser runtime. Deployment is blocked.'
    if (script.count('fetch(') != 1 or 'https://api.reclub.co${path}' not in script
            or 'window.CourtsideBrowser=' not in script):
        return 'The browser queue does not use the fixed direct Reclub boundary. Deployment is blocked.'
    if 'api' not in ignored or 'web/organizer.html' not in ignored or 'web/app.js' in ignored:
        return 'The browser assets or server-route exclusions are incorrect. Deployment is blocked.'
    return None


def main():
    error = validate_website(Path(__file__).resolve().parent.parent)
    if error:
        print(error)
        return 1
    print('Browser organizer and direct Reclub import are present; server routes are excluded.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
