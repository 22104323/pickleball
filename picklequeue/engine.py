"""SQLite-backed single-operator queue with transactional assignments."""

import csv
import io
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .matching import choose_game
from .ratings import Rating, doubles_opponent, update_rating


class Problem(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def integer(value, label, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise Problem(f'{label} must be an integer from {minimum} to {maximum}.')
    return value


def text(value, label, limit=120):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise Problem(f'{label} is required and must be at most {limit} printable characters.')
    return value.strip()


class Engine:
    def __init__(self, path, clock=time.time):
        self.path = str(path)
        self.clock = clock
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise Problem('Unsupported database version; no data was changed.')
            db.executescript(Path(__file__).with_name('schema.sql').read_text())

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10, factory=Connection)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        return db

    @contextmanager
    def transaction(self, id_session, revision):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            session = db.execute('SELECT * FROM sessions WHERE id=?', (id_session,)).fetchone()
            if not session:
                raise Problem('Session not found.', 404)
            if type(revision) is not int or revision != session['revision']:
                raise Problem('This session changed. Refresh and try again.', 409)
            if session['status'] != 'active':
                raise Problem('This session is closed.', 409)
            yield db, session
            db.execute('UPDATE sessions SET revision=revision+1 WHERE id=?', (id_session,))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def audit(self, db, id_session, action, detail):
        db.execute('INSERT INTO audit_log(id_session,action,detail,created_at) VALUES(?,?,?,?)',
                   (id_session, action, json.dumps(detail, sort_keys=True), self.clock()))

    def list_sessions(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM sessions ORDER BY id DESC')]

    def create_session(self, data):
        name = text(data.get('name'), 'Session name')
        courts = integer(data.get('court_count', 2), 'Courts', 1, 8)
        maximum = integer(data.get('max_players', 30), 'Capacity', 4, 200)
        start = data.get('starts_at', self.clock())
        if isinstance(start, bool) or not isinstance(start, (int, float)) or not 0 < start < 4102444800:
            raise Problem('Start time must be a valid Unix timestamp before 2100.')
        with self.connect() as db:
            id_session = db.execute('INSERT INTO sessions(name,starts_at,court_count,max_players,created_at) VALUES(?,?,?,?,?)',
                                    (name, start, courts, maximum, self.clock())).lastrowid
            self.audit(db, id_session, 'session.created', {'court_count': courts, 'max_players': maximum})
        return id_session

    def state(self, id_session):
        with self.connect() as db:
            db.execute('BEGIN')
            session = db.execute('SELECT * FROM sessions WHERE id=?', (id_session,)).fetchone()
            if not session:
                raise Problem('Session not found.', 404)
            players = [dict(p) for p in db.execute('''SELECT r.*, m.name, m.source, m.external_id,
                m.rating, m.deviation, m.volatility, m.rated_games
                FROM roster r JOIN members m ON m.id=r.id_member WHERE r.id_session=?
                ORDER BY CASE WHEN r.ticket IS NULL THEN 1 ELSE 0 END,r.ticket,r.id''', (id_session,))]
            positions = 0
            for p in players:
                p['position'] = None
                if p['queue_state'] == 'waiting':
                    positions += 1
                    p['position'] = positions
                p['wait_minutes'] = max(0, (self.clock() - p['queued_at']) / 60) if p['queued_at'] else 0
                p['eligible'] = p['membership'] == 'active' and p['waiver'] == 'valid'
                p['provisional'] = p['rated_games'] < 10
                p['band'] = 'Beginner' if p['rating'] < 1100 else 'Intermediate' if p['rating'] < 1450 else 'Advanced' if p['rating'] < 1750 else 'Competitive'
            games = []
            for row in db.execute('SELECT * FROM games WHERE id_session=? ORDER BY id DESC', (id_session,)):
                game = dict(row)
                game['players'] = [dict(p) for p in db.execute('''SELECT gp.*,m.name FROM game_players gp
                    JOIN roster r ON r.id=gp.id_roster JOIN members m ON m.id=r.id_member
                    WHERE gp.id_game=? ORDER BY gp.side,gp.id_roster''', (game['id'],))]
                games.append(game)
            audit = [dict(a) for a in db.execute('SELECT * FROM audit_log WHERE id_session=? ORDER BY id DESC LIMIT 30', (id_session,))]
            completed = [g for g in games if g['status'] == 'completed']
            metrics = {'present': sum(p['attendance'] == 'present' for p in players),
                       'waiting': positions, 'on_court': sum(p['queue_state'] in ('assigned', 'playing') for p in players),
                       'completed_games': len(completed), 'no_shows': sum(p['attendance'] == 'no_show' for p in players),
                       'late': sum(p['is_late'] for p in players),
                       'stomp_rate': sum(not .35 <= g['expected_a'] <= .65 for g in completed) / len(completed) if completed else None}
            return {'session': dict(session), 'players': players, 'games': games, 'metrics': metrics, 'audit': audit}

    def import_roster(self, id_session, revision, content, source='reclub', club_key=''):
        if source not in ('reclub', 'manual', 'demo'):
            raise Problem('Unknown roster source.')
        club_key = text(club_key, 'Club identifier')
        if not isinstance(content, str) or len(content) > 200000:
            raise Problem('CSV must be under 200 KB.')
        try:
            reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff')), strict=True)
            required = {'external_id', 'name', 'rsvp', 'membership', 'waiver'}
            if not reader.fieldnames or not required <= set(reader.fieldnames) or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise Problem('CSV needs unique headers: external_id,name,rsvp,membership,waiver; optional initial_rating.')
            rows = list(reader)
        except csv.Error as error:
            raise Problem('CSV could not be parsed.') from error
        if not rows or len(rows) > 200:
            raise Problem('Import between 1 and 200 players.')
        validated, seen = [], set()
        for row in rows:
            if None in row:
                raise Problem('A CSV row has more values than the header.')
            external = text(row.get('external_id'), 'External player ID')
            if external in seen:
                raise Problem(f'Duplicate external ID in CSV: {external}')
            seen.add(external)
            name = text(row.get('name'), 'Player name', 80)
            rsvp, membership, waiver = ((row.get(key) or '').strip().lower() for key in ('rsvp', 'membership', 'waiver'))
            if rsvp not in ('yes', 'no', 'waitlist', 'cancelled') or membership not in ('active', 'expired', 'unknown') or waiver not in ('valid', 'missing', 'unknown'):
                raise Problem('Invalid RSVP, membership, or waiver status in CSV.')
            try:
                rating = float(row.get('initial_rating') or 1200)
            except (TypeError, ValueError):
                raise Problem('Initial rating must be a number.')
            if not 0 <= rating <= 4000:
                raise Problem('Initial rating must be between 0 and 4000.')
            validated.append((external, name, rsvp, membership, waiver, rating))
        with self.transaction(id_session, revision) as (db, session):
            if source != 'demo' and db.execute("SELECT 1 FROM roster r JOIN members m ON m.id=r.id_member WHERE r.id_session=? AND m.source='demo' LIMIT 1", (id_session,)).fetchone():
                raise Problem('Demo sessions cannot mix with imported club players. Create a new session for your roster.', 409)
            for external, name, rsvp, membership, waiver, rating in validated:
                member = db.execute('SELECT * FROM members WHERE source=? AND club_key=? AND external_id=?', (source, club_key, external)).fetchone()
                if member is None:
                    id_member = db.execute('INSERT INTO members(source,club_key,external_id,name,rating) VALUES(?,?,?,?,?)',
                                          (source, club_key, external, name, rating)).lastrowid
                    member = db.execute('SELECT * FROM members WHERE id=?', (id_member,)).fetchone()
                else:
                    id_member = member['id']
                    db.execute('UPDATE members SET name=? WHERE id=?', (name, id_member))
                old = db.execute('SELECT * FROM roster WHERE id_session=? AND id_member=?', (id_session, id_member)).fetchone()
                if old and old['queue_state'] in ('assigned', 'playing') and (membership != 'active' or waiver != 'valid'):
                    raise Problem('An assigned player became ineligible. Cancel their assignment or finish the game before importing.', 409)
                db.execute('''INSERT INTO roster(id_session,id_member,rsvp,membership,waiver,base_rating,base_deviation,base_volatility)
                    VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id_session,id_member) DO UPDATE SET
                    rsvp=excluded.rsvp,membership=excluded.membership,waiver=excluded.waiver''',
                    (id_session, id_member, rsvp, membership, waiver, member['rating'], member['deviation'], member['volatility']))
                if old and old['queue_state'] == 'waiting' and (membership != 'active' or waiver != 'valid'):
                    db.execute("UPDATE roster SET queue_state='off',ticket=NULL,queued_at=NULL WHERE id=?", (old['id'],))
            self.audit(db, id_session, 'roster.imported', {'source': source, 'rows': len(rows)})
        return len(rows)

    def demo(self, id_session, revision):
        with self.connect() as db:
            if db.execute('SELECT COUNT(*) FROM roster WHERE id_session=?', (id_session,)).fetchone()[0]:
                raise Problem('Load demo players into an empty session only.', 409)
        names = ['Avery', 'Blake', 'Cameron', 'Drew', 'Ellis', 'Frankie', 'Gray', 'Harper', 'Indigo', 'Jules', 'Kai', 'Lane',
                 'Morgan', 'Noel', 'Oak', 'Parker', 'Quinn', 'Reese', 'Sage', 'Taylor', 'Uma', 'Vale', 'Winter', 'Xan', 'Yael', 'Zion', 'Alex', 'Briar', 'Casey', 'Devon']
        ratings = [1800,1750,1200,1150,1350,1400,1250,1300,1500,1550,1000,1050,1600,1450,1100]
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(['external_id', 'name', 'rsvp', 'membership', 'waiver', 'initial_rating'])
        for i, name in enumerate(names):
            writer.writerow([f'demo-{i+1:02}', f'{name} (demo)', 'yes', 'active', 'valid', ratings[i % len(ratings)]])
        return self.import_roster(id_session, revision, stream.getvalue(), 'demo', f'demo-session-{id_session}')

    def player_action(self, id_session, revision, id_roster, action, data=None):
        data = data or {}
        with self.transaction(id_session, revision) as (db, session):
            player = db.execute('SELECT * FROM roster WHERE id=? AND id_session=?', (id_roster, id_session)).fetchone()
            if not player:
                raise Problem('Player not found.', 404)
            now = self.clock()
            if action == 'checkin':
                if player['attendance'] == 'present':
                    raise Problem('Player is already checked in.', 409)
                if player['queue_state'] in ('assigned', 'playing'):
                    raise Problem('Player is already assigned.', 409)
                present = db.execute("SELECT COUNT(*) FROM roster WHERE id_session=? AND attendance='present'", (id_session,)).fetchone()[0]
                if present >= session['max_players']:
                    raise Problem('Session capacity is full.', 409)
                other = db.execute('''SELECT r.id FROM roster r JOIN sessions s ON s.id=r.id_session
                    WHERE r.id_member=? AND r.id_session!=? AND s.status='active'
                    AND (r.attendance='present' OR r.games_played>0)''', (player['id_member'], id_session)).fetchone()
                if other:
                    raise Problem('Close or leave the other active session before checking in here; played sessions must be closed.', 409)
                member = db.execute('SELECT * FROM members WHERE id=?', (player['id_member'],)).fetchone()
                db.execute('''UPDATE roster SET attendance='present',checked_in_at=?,checked_out_at=NULL,is_late=?,
                    base_rating=?,base_deviation=?,base_volatility=? WHERE id=?''',
                    (now, now > session['starts_at'] + 15 * 60, player['base_rating'] if player['games_played'] else member['rating'],
                     player['base_deviation'] if player['games_played'] else member['deviation'],
                     player['base_volatility'] if player['games_played'] else member['volatility'], id_roster))
                if player['membership'] == 'active' and player['waiver'] == 'valid':
                    self.enqueue(db, id_session, id_roster)
            elif action == 'eligibility':
                membership, waiver = data.get('membership'), data.get('waiver')
                if membership not in ('active','expired','unknown') or waiver not in ('valid','missing','unknown'):
                    raise Problem('Choose valid membership and waiver states.')
                if player['queue_state'] in ('assigned', 'playing'):
                    raise Problem('Cancel the assignment or complete the game before changing eligibility.', 409)
                db.execute('UPDATE roster SET membership=?,waiver=? WHERE id=?', (membership, waiver, id_roster))
                if membership != 'active' or waiver != 'valid':
                    db.execute("UPDATE roster SET queue_state='off',ticket=NULL,queued_at=NULL WHERE id=?", (id_roster,))
                elif player['attendance'] == 'present' and player['queue_state'] == 'off':
                    self.enqueue(db, id_session, id_roster)
            elif action in ('pause', 'resume', 'checkout'):
                if player['queue_state'] in ('assigned', 'playing'):
                    raise Problem('Cancel the assignment or finish the game before leaving the queue.', 409)
                if action == 'resume':
                    if player['attendance'] != 'present' or player['membership'] != 'active' or player['waiver'] != 'valid':
                        raise Problem('Player must be present with active membership and a valid waiver.')
                    if player['queue_state'] == 'waiting':
                        raise Problem('Player is already queued.', 409)
                    self.enqueue(db, id_session, id_roster)
                else:
                    db.execute("UPDATE roster SET queue_state='off',ticket=NULL,queued_at=NULL WHERE id=?", (id_roster,))
                    if action == 'checkout':
                        if player['attendance'] != 'present':
                            raise Problem('Player is not checked in.', 409)
                        db.execute("UPDATE roster SET attendance='left',checked_out_at=? WHERE id=?", (now, id_roster))
            else:
                raise Problem('Unknown player action.')
            self.audit(db, id_session, f'player.{action}', {'id_roster': id_roster})

    def enqueue(self, db, id_session, id_roster):
        ticket = db.execute('UPDATE sessions SET next_ticket=next_ticket+1 WHERE id=? RETURNING next_ticket', (id_session,)).fetchone()[0]
        db.execute("UPDATE roster SET queue_state='waiting',ticket=?,queued_at=? WHERE id=?", (ticket, self.clock(), id_roster))

    def histories(self, db, id_session):
        partners, opponents = {}, {}
        local_roster = {p['id_member']:p['id'] for p in db.execute('SELECT id,id_member FROM roster WHERE id_session=?', (id_session,))}
        recent = db.execute('''SELECT DISTINCT g.id FROM games g JOIN game_players gp ON gp.id_game=g.id
            JOIN roster old ON old.id=gp.id_roster JOIN roster current ON current.id_member=old.id_member
            WHERE g.status='completed' AND current.id_session=? ORDER BY g.id DESC LIMIT 10''', (id_session,)).fetchall()
        for game in recent:
            rows = db.execute('''SELECT r.id_member,gp.side FROM game_players gp
                JOIN roster r ON r.id=gp.id_roster WHERE gp.id_game=?''', (game['id'],)).fetchall()
            for i, a in enumerate(rows):
                for b in rows[i+1:]:
                    if a['id_member'] not in local_roster or b['id_member'] not in local_roster:
                        continue
                    key = tuple(sorted((local_roster[a['id_member']], local_roster[b['id_member']])))
                    counts = partners if a['side'] == b['side'] else opponents
                    counts[key] = counts.get(key, 0) + 1
        return partners, opponents

    def fill_courts(self, id_session, revision):
        assigned, reasons = [], []
        with self.transaction(id_session, revision) as (db, session):
            used = {g[0] for g in db.execute("SELECT court FROM games WHERE id_session=? AND status IN ('assigned','playing')", (id_session,))}
            partners, opponents = self.histories(db, id_session)
            for court in range(1, session['court_count']+1):
                if court in used:
                    continue
                players = [dict(p) for p in db.execute('''SELECT r.id,r.ticket,r.games_played,m.rating,m.rated_games FROM roster r
                    JOIN members m ON m.id=r.id_member WHERE r.id_session=? AND r.attendance='present'
                    AND r.queue_state='waiting' AND r.membership='active' AND r.waiver='valid' ORDER BY r.ticket,r.id''', (id_session,))]
                match = choose_game(players, partners, opponents)
                if match is None:
                    reasons.append(f'Court {court}: need four eligible players.' if len(players) < 4 else f'Court {court}: no balanced game includes the longest-waiting player. No one was skipped.')
                    break
                team_a, team_b = match['teams']
                mean_a, mean_b = (sum(p['rating'] for p in t) / 2 for t in match['teams'])
                id_game = db.execute('''INSERT INTO games(id_session,court,assigned_at,mean_a,mean_b,expected_a,cost,reason)
                    VALUES(?,?,?,?,?,?,?,?)''', (id_session, court, self.clock(), mean_a, mean_b, match['expected'], match['cost'], match['reason'])).lastrowid
                for side, team in (('a', team_a), ('b', team_b)):
                    for p in team:
                        member = db.execute('''SELECT m.* FROM members m JOIN roster r ON r.id_member=m.id WHERE r.id=?''', (p['id'],)).fetchone()
                        db.execute('INSERT INTO active_assignments(id_roster,id_game) VALUES(?,?)', (p['id'], id_game))
                        db.execute('INSERT INTO game_players(id_game,id_roster,side,rating,deviation,volatility) VALUES(?,?,?,?,?,?)',
                                   (id_game, p['id'], side, member['rating'], member['deviation'], member['volatility']))
                        db.execute("UPDATE roster SET queue_state='assigned' WHERE id=?", (p['id'],))
                assigned.append(id_game)
            if assigned:
                self.audit(db, id_session, 'courts.assigned', {'games': assigned})
        return {'assigned': assigned, 'messages': reasons}

    def game_action(self, id_session, revision, id_game, action, data=None):
        data = data or {}
        with self.transaction(id_session, revision) as (db, session):
            game = db.execute('SELECT * FROM games WHERE id=? AND id_session=?', (id_game, id_session)).fetchone()
            if not game:
                raise Problem('Game not found.', 404)
            players = db.execute('SELECT r.* FROM roster r JOIN game_players gp ON gp.id_roster=r.id WHERE gp.id_game=? ORDER BY r.ticket,r.id', (id_game,)).fetchall()
            if action == 'start':
                if game['status'] != 'assigned':
                    raise Problem('Only assigned games can start.', 409)
                if len(players) != 4 or any(p['attendance'] != 'present' or p['membership'] != 'active' or p['waiver'] != 'valid' for p in players):
                    raise Problem('Four present, eligible players are required.', 409)
                db.execute("UPDATE games SET status='playing',started_at=? WHERE id=?", (self.clock(), id_game))
                db.execute("UPDATE roster SET queue_state='playing' WHERE id IN (SELECT id_roster FROM game_players WHERE id_game=?)", (id_game,))
            elif action == 'complete':
                if game['status'] != 'playing':
                    raise Problem('Start the game before recording its result.', 409)
                score_a = integer(data.get('score_a'), 'Team A score', 0, 99)
                score_b = integer(data.get('score_b'), 'Team B score', 0, 99)
                if score_a == score_b:
                    raise Problem('A completed doubles game needs a winner.')
                db.execute("UPDATE games SET status='completed',score_a=?,score_b=?,completed_at=? WHERE id=?", (score_a, score_b, self.clock(), id_game))
                db.execute('DELETE FROM active_assignments WHERE id_game=?', (id_game,))
                for p in players:
                    db.execute('UPDATE roster SET games_played=games_played+1 WHERE id=?', (p['id'],))
                    if p['attendance'] == 'present' and p['membership'] == 'active' and p['waiver'] == 'valid':
                        self.enqueue(db, id_session, p['id'])
                    else:
                        db.execute("UPDATE roster SET queue_state='off',ticket=NULL,queued_at=NULL WHERE id=?", (p['id'],))
            elif action == 'cancel':
                if game['status'] not in ('assigned','playing'):
                    raise Problem('This game is already finished.', 409)
                reason = text(data.get('reason'), 'Cancellation reason', 200)
                db.execute("UPDATE games SET status='cancelled',completed_at=? WHERE id=?", (self.clock(), id_game))
                db.execute('DELETE FROM active_assignments WHERE id_game=?', (id_game,))
                for p in players:
                    db.execute("UPDATE roster SET queue_state='waiting' WHERE id=?", (p['id'],))
                self.audit(db, id_session, 'game.cancelled', {'id_game': id_game, 'reason': reason})
            else:
                raise Problem('Unknown game action.')
            if action != 'cancel':
                self.audit(db, id_session, f'game.{action}', {'id_game': id_game})

    def reconcile(self, id_session, revision):
        with self.transaction(id_session, revision) as (db, session):
            if self.clock() < session['starts_at'] + 30 * 60:
                raise Problem('No-show reconciliation opens 30 minutes after the session start.')
            count = db.execute("UPDATE roster SET attendance='no_show' WHERE id_session=? AND rsvp='yes' AND attendance='absent' AND checked_in_at IS NULL", (id_session,)).rowcount
            self.audit(db, id_session, 'attendance.reconciled', {'no_shows': count})
        return count

    def close_session(self, id_session, revision):
        with self.transaction(id_session, revision) as (db, session):
            if db.execute("SELECT COUNT(*) FROM games WHERE id_session=? AND status IN ('assigned','playing')", (id_session,)).fetchone()[0]:
                raise Problem('Complete or cancel every active court before closing.', 409)
            players = db.execute('SELECT * FROM roster WHERE id_session=?', (id_session,)).fetchall()
            bases = {p['id']: Rating(p['base_rating'],p['base_deviation'],p['base_volatility']) for p in players}
            observations = {p['id']: [] for p in players}
            for game in db.execute("SELECT * FROM games WHERE id_session=? AND status='completed'", (id_session,)):
                gp = db.execute('SELECT * FROM game_players WHERE id_game=?', (game['id'],)).fetchall()
                for p in gp:
                    partner = next(q for q in gp if q['side'] == p['side'] and q['id_roster'] != p['id_roster'])
                    opposition = [bases[q['id_roster']] for q in gp if q['side'] != p['side']]
                    opponent = doubles_opponent(bases[p['id_roster']], bases[partner['id_roster']], opposition)
                    won = (game['score_a'] > game['score_b']) == (p['side'] == 'a')
                    observations[p['id_roster']].append((opponent, int(won)))
            for p in players:
                results = observations[p['id']]
                if not results:
                    continue
                old = bases[p['id']]
                current = db.execute('SELECT * FROM members WHERE id=?', (p['id_member'],)).fetchone()
                if abs(current['rating'] - old.value) > .000001 or abs(current['deviation'] - old.deviation) > .000001 or abs(current['volatility'] - old.volatility) > .000001:
                    raise Problem('Rating changed in another session; resolve the overlapping period before closing.', 409)
                updated = update_rating(old, results)
                updated = Rating(max(0, min(4000, updated.value)), min(350, updated.deviation), updated.volatility)
                db.execute('''INSERT INTO rating_history(id_session,id_member,old_rating,new_rating,old_deviation,new_deviation,old_volatility,new_volatility)
                    VALUES(?,?,?,?,?,?,?,?)''', (id_session,p['id_member'],old.value,updated.value,old.deviation,updated.deviation,old.volatility,updated.volatility))
                db.execute('UPDATE members SET rating=?,deviation=?,volatility=?,rated_games=rated_games+? WHERE id=?',
                           (updated.value, updated.deviation, updated.volatility, len(results), p['id_member']))
            now = self.clock()
            if now >= session['starts_at'] + 30 * 60:
                db.execute("UPDATE roster SET attendance='no_show' WHERE id_session=? AND rsvp='yes' AND attendance='absent' AND checked_in_at IS NULL", (id_session,))
            db.execute("UPDATE roster SET attendance=CASE WHEN attendance='present' THEN 'left' ELSE attendance END,checked_out_at=CASE WHEN attendance='present' THEN ? ELSE checked_out_at END,queue_state='off',ticket=NULL,queued_at=NULL WHERE id_session=?", (now,id_session))
            db.execute("UPDATE sessions SET status='closed' WHERE id=?", (id_session,))
            self.audit(db, id_session, 'session.closed', {'rated_players': sum(bool(r) for r in observations.values())})
