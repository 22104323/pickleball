"""Loopback-only organizer web app with a read-only public Reclub preview."""

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .engine import Engine, Problem

WEB = Path(__file__).resolve().parent.parent / 'web'


def serve(engine, port=8080):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def send(self, status, body, content_type='application/json; charset=utf-8'):
            if not isinstance(body, bytes):
                body = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')

        def do_GET(self):
            try:
                if not self.valid_host():
                    raise Problem('Use the loopback address printed by the server.', 403)
                path = urlsplit(self.path).path
                if path == '/api/sessions':
                    return self.send(200, {'sessions': engine.list_sessions()})
                if path.startswith('/api/sessions/'):
                    try:
                        id_session = int(path.rsplit('/',1)[1])
                    except ValueError:
                        raise Problem('Session not found.', 404)
                    return self.send(200, engine.state(id_session))
                assets = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css', '/favicon.svg':'favicon.svg', '/fonts/patrick-hand-latin.woff2':'fonts/patrick-hand-latin.woff2'}
                if path not in assets:
                    raise Problem('Page not found.', 404)
                file = WEB / assets[path]
                return self.send(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
            except Problem as error:
                self.send(error.status, {'error': str(error)})

        def do_POST(self):
            try:
                if not self.valid_host():
                    raise Problem('Invalid host.', 403)
                origin = self.headers.get('Origin')
                if origin and origin not in (f'http://127.0.0.1:{port}', f'http://localhost:{port}'):
                    raise Problem('Cross-origin changes are not accepted.', 403)
                if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                    raise Problem('Expected JSON.', 415)
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                except ValueError:
                    raise Problem('Invalid request length.')
                if not 0 < length <= 250000:
                    raise Problem('Request must be between 1 byte and 250 KB.', 413)
                try:
                    data = json.loads(self.rfile.read(length), parse_constant=lambda x: (_ for _ in ()).throw(ValueError()))
                except (ValueError, UnicodeDecodeError):
                    raise Problem('Invalid JSON.')
                if not isinstance(data, dict):
                    raise Problem('Expected a JSON object.')
                path = urlsplit(self.path).path
                if path == '/api/sessions':
                    return self.send(201, engine.state(engine.create_session(data)))
                if path == '/api/reclub/preview':
                    from .reclub import preview_event
                    return self.send(200, preview_event(data.get('url')))
                pieces = path.strip('/').split('/')
                if len(pieces) != 4 or pieces[:2] != ['api','sessions']:
                    raise Problem('Action not found.', 404)
                try:
                    id_session = int(pieces[2])
                except ValueError:
                    raise Problem('Session not found.', 404)
                revision, action = data.get('revision'), pieces[3]
                notice = ''
                if action == 'import':
                    count = engine.import_roster(id_session,revision,data.get('csv'),data.get('source','reclub'),data.get('club_key',''))
                    notice = f'Imported {count} roster records. Check-ins were preserved.'
                elif action == 'import-reviewed':
                    count = engine.import_reviewed(id_session,revision,data.get('players'),data.get('pairs'),data.get('source','manual'),data.get('club_key','manual'))
                    notice = f'Added {count} players to Not Yet Here. Check them in when they arrive.'
                elif action == 'demo':
                    engine.demo(id_session, revision)
                    notice = 'Loaded 30 synthetic demo players. Check them in to start.'
                elif action == 'checkin-all':
                    count = engine.checkin_all(id_session,revision)
                    notice = f'Checked in {count} players. Eligibility is still required to join the queue.'
                elif action == 'player':
                    id_roster = data.get('id_roster')
                    if type(id_roster) is not int:
                        raise Problem('Invalid player ID.')
                    engine.player_action(id_session,revision,id_roster,data.get('action'),data)
                elif action == 'pair':
                    pair_action = data.get('action')
                    if pair_action == 'pair':
                        engine.pair_players(id_session,revision,data.get('id_a'),data.get('id_b'))
                    elif pair_action == 'unpair':
                        engine.unpair_player(id_session,revision,data.get('id_roster'))
                    else:
                        raise Problem('Unknown pairing action.')
                elif action == 'fill':
                    result = engine.fill_courts(id_session,revision)
                    notice = f"Assigned {len(result['assigned'])} court(s). " + ' '.join(result['messages'])
                elif action == 'game':
                    if type(data.get('id_game')) is not int:
                        raise Problem('Invalid game ID.')
                    engine.game_action(id_session,revision,data['id_game'],data.get('action'),data)
                    notice = {'swap_winner': 'Winner corrected. Games played and Up Next teams are unchanged.',
                              'rebuild': 'Up Next rebuilt using current results and queue rules.'}.get(data.get('action'), '')
                elif action == 'reconcile':
                    count = engine.reconcile(id_session, revision)
                    notice = f'Marked {count} absent RSVPs as no-shows. No penalties applied.'
                elif action == 'close':
                    engine.close_session(id_session, revision)
                    notice = 'Session closed. One Glicko-2 period was applied to completed results.'
                else:
                    raise Problem('Action not found.', 404)
                self.send(200, {**engine.state(id_session), 'notice': notice})
            except Problem as error:
                self.send(error.status, {'error': str(error)})
            except Exception:
                self.send(500, {'error': 'The change could not be completed. Refresh the session and try again.'})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    port = server.server_address[1]
    return server


def main():
    parser = argparse.ArgumentParser(description='Local pickleball organizer queue')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--database', default='data/pickleball.sqlite3')
    options = parser.parse_args()
    engine = Engine(options.database)
    server = serve(engine, options.port)
    print(f'Pickleball queue: http://127.0.0.1:{options.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
