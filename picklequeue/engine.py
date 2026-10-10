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

MODES = ('balanced','social_mix','skill_separated','winners_losers','skill_courts',
         'mixed_doubles','king_queen','club_wars')


def skill_band(rating):
    return 'Beginner' if rating < 1100 else 'Intermediate' if rating < 1450 else 'Advanced' if rating < 1750 else 'Competitive'


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
            if version not in (0, 1, 2):
                raise Problem('Unsupported database version; no data was changed.')
            if version == 1:
                db.execute('BEGIN IMMEDIATE')
                db.execute("ALTER TABLE sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'balanced' CHECK (mode IN ('balanced','social_mix','skill_separated','winners_losers','skill_courts','mixed_doubles','king_queen','club_wars'))")
                db.execute("ALTER TABLE members ADD COLUMN gender TEXT CHECK (gender IN ('M','F'))")
                db.execute('ALTER TABLE roster ADD COLUMN club_group TEXT')
                db.execute('PRAGMA user_version = 2')
                db.commit()
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
        mode = data.get('mode', 'balanced')
        if mode not in MODES:
            raise Problem('Choose a supported play mode.')
        start = data.get('starts_at', self.clock())
        if isinstance(start, bool) or not isinstance(start, (int, float)) or not 0 < start < 4102444800:
            raise Problem('Start time must be a valid Unix timestamp before 2100.')
        with self.connect() as db:
            id_session = db.execute('INSERT INTO sessions(name,starts_at,court_count,max_players,mode,created_at) VALUES(?,?,?,?,?,?)',
                                    (name, start, courts, maximum, mode, self.clock())).lastrowid
            self.audit(db, id_session, 'session.created', {'court_count': courts, 'max_players': maximum})
        return id_session

    def state(self, id_session):
        with self.connect() as db:
            db.execute('BEGIN')
            session = db.execute('SELECT * FROM sessions WHERE id=?', (id_session,)).fetchone()
            if not session:
                raise Problem('Session not found.', 404)
            players = [dict(p) for p in db.execute('''SELECT r.*, m.name, m.source, m.external_id,
                m.rating, m.deviation, m.volatility, m.rated_games, m.gender,
                partner.id AS paired_roster_id, partner_member.name AS partner_name
                FROM roster r JOIN members m ON m.id=r.id_member
                LEFT JOIN team_pairs tp ON tp.id_session=r.id_session AND r.id IN (tp.id_player_a,tp.id_player_b)
                LEFT JOIN roster partner ON partner.id=CASE WHEN r.id=tp.id_player_a THEN tp.id_player_b ELSE tp.id_player_a END
                LEFT JOIN members partner_member ON partner_member.id=partner.id_member
                WHERE r.id_session=?
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
                p['band'] = skill_band(p['rating'])
            games = []
            for row in db.execute('SELECT * FROM games WHERE id_session=? ORDER BY id DESC', (id_session,)):
                game = dict(row)
                game['players'] = [dict(p) for p in db.execute('''SELECT gp.*,m.name,m.gender FROM game_players gp
                    JOIN roster r ON r.id=gp.id_roster JOIN members m ON m.id=r.id_member
                    WHERE gp.id_game=? ORDER BY gp.side,gp.id_roster''', (game['id'],))]
                games.append(game)
            audit = [dict(a) for a in db.execute('SELECT * FROM audit_log WHERE id_session=? ORDER BY id DESC LIMIT 30', (id_session,))]
            completed = [g for g in games if g['status'] == 'completed']
            wins, latest = {}, {}
            for game in completed:
                for player in game['players']:
                    won = (game['score_a'] > game['score_b']) == (player['side'] == 'a')
                    id_player = player['id_roster']
                    wins[id_player] = wins.get(id_player, 0) + int(won)
                    latest.setdefault(id_player, 'winner' if won else 'loser')
            standings = []
            for player in players:
                player['wins'] = wins.get(player['id'], 0)
                player['losses'] = player['games_played'] - player['wins']
                player['last_outcome'] = latest.get(player['id'])
                standings.append({key: player[key] for key in ('id','name','wins','losses','games_played')})
            standings.sort(key=lambda player: (-player['wins'], player['games_played'] == 0, player['losses'], player['name'].casefold(), player['id']))
            metrics = {'present': sum(p['attendance'] == 'present' for p in players),
                       'waiting': positions, 'on_court': sum(p['queue_state'] in ('assigned', 'playing') for p in players),
                       'completed_games': len(completed), 'no_shows': sum(p['attendance'] == 'no_show' for p in players),
                       'late': sum(p['is_late'] for p in players),
                       'stomp_rate': sum(not .35 <= g['expected_a'] <= .65 for g in completed) / len(completed) if completed else None}
            return {'session': dict(session), 'players': players, 'games': games, 'metrics': metrics, 'standings': standings, 'audit': audit}

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
                raise Problem('CSV needs unique headers: external_id,name,rsvp,membership,waiver; optional initial_rating,gender,club_group.')
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
            gender = (row.get('gender') or '').strip().upper() or None
            if gender not in (None, 'M', 'F'):
                raise Problem('Gender must be M, F, or blank; do not infer it from a name.')
            club_group = (row.get('club_group') or '').strip() or None
            if club_group is not None:
                club_group = text(club_group, 'Club group', 40)
            validated.append((external, name, rsvp, membership, waiver, rating, gender, club_group))
        with self.transaction(id_session, revision) as (db, session):
            if source != 'demo' and db.execute("SELECT 1 FROM roster r JOIN members m ON m.id=r.id_member WHERE r.id_session=? AND m.source='demo' LIMIT 1", (id_session,)).fetchone():
                raise Problem('Demo sessions cannot mix with imported club players. Create a new session for your roster.', 409)
            for external, name, rsvp, membership, waiver, rating, gender, club_group in validated:
                member = db.execute('SELECT * FROM members WHERE source=? AND club_key=? AND external_id=?', (source, club_key, external)).fetchone()
                if member is None:
                    id_member = db.execute('INSERT INTO members(source,club_key,external_id,name,rating,gender) VALUES(?,?,?,?,?,?)',
                                          (source, club_key, external, name, rating, gender)).lastrowid
                    member = db.execute('SELECT * FROM members WHERE id=?', (id_member,)).fetchone()
                else:
                    id_member = member['id']
                    if gender is None:
                        db.execute('UPDATE members SET name=? WHERE id=?', (name, id_member))
                    else:
                        db.execute('UPDATE members SET name=?,gender=? WHERE id=?', (name, gender, id_member))
                old = db.execute('SELECT * FROM roster WHERE id_session=? AND id_member=?', (id_session, id_member)).fetchone()
                if old and old['queue_state'] in ('assigned', 'playing') and (membership != 'active' or waiver != 'valid'):
                    raise Problem('An assigned player became ineligible. Cancel their assignment or finish the game before importing.', 409)
                db.execute('''INSERT INTO roster(id_session,id_member,rsvp,membership,waiver,base_rating,base_deviation,base_volatility,club_group)
                    VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id_session,id_member) DO UPDATE SET
                    rsvp=excluded.rsvp,membership=excluded.membership,waiver=excluded.waiver,
                    club_group=COALESCE(excluded.club_group,roster.club_group)''',
                    (id_session, id_member, rsvp, membership, waiver, member['rating'], member['deviation'], member['volatility'], club_group))
                if old and old['queue_state'] == 'waiting' and (membership != 'active' or waiver != 'valid'):
                    db.execute("UPDATE roster SET queue_state='off',ticket=NULL,queued_at=NULL WHERE id=?", (old['id'],))
            self.audit(db, id_session, 'roster.imported', {'source': source, 'rows': len(rows)})
        return len(rows)

    def import_reviewed(self, id_session, revision, players, pairs=None, source='manual', club_key='manual'):
        if source not in ('reclub','manual'):
            raise Problem('Reviewed imports must be manual or Reclub players.')
        club_key = text(club_key, 'Club identifier')
        if not isinstance(players, list) or not 1 <= len(players) <= 200:
            raise Problem('Review between 1 and 200 players before adding them.')
        if pairs is None:
            pairs = []
        if not isinstance(pairs, list) or len(pairs) > 100:
            raise Problem('Invalid player pair list.')
        validated, seen = [], set()
        for player in players:
            if not isinstance(player, dict):
                raise Problem('Each reviewed player must be an object.')
            external = text(player.get('external_id'), 'Player ID', 120)
            if external in seen:
                raise Problem('Each reviewed player needs a unique player ID.')
            seen.add(external)
            name = text(player.get('name'), 'Player name', 80)
            rating = player.get('rating')
            if rating is not None:
                if isinstance(rating, bool) or not isinstance(rating, (int,float)) or not 0 <= rating <= 4000:
                    raise Problem('Player ratings must be from 0 to 4000.')
                rating = float(rating)
            gender = player.get('gender') or None
            if gender not in (None,'M','F'):
                raise Problem('Choose M, F, or no gender; do not infer it from a name.')
            group = player.get('club_group') or None
            if group is not None:
                group = text(group, 'Club group', 40)
            validated.append({'external':external,'name':name,'rating':rating,'gender':gender,'group':group})
        validated_pairs, paired = [], set()
        for pair in pairs:
            if not isinstance(pair, list) or len(pair) != 2 or any(not isinstance(value, str) for value in pair) or pair[0] == pair[1] or pair[0] not in seen or pair[1] not in seen:
                raise Problem('Every pair must contain two different selected players.')
            if pair[0] in paired or pair[1] in paired:
                raise Problem('A player can have only one partner.')
            paired.update(pair)
            validated_pairs.append(tuple(pair))
        with self.transaction(id_session, revision) as (db, _session):
            if db.execute("SELECT 1 FROM roster r JOIN members m ON m.id=r.id_member WHERE r.id_session=? AND m.source='demo' LIMIT 1", (id_session,)).fetchone():
                raise Problem('Demo sessions cannot mix with imported club players. Create a new session for your roster.', 409)
            roster_by_external = {}
            for player in validated:
                member = db.execute('SELECT * FROM members WHERE source=? AND club_key=? AND external_id=?',
                                     (source,club_key,player['external'])).fetchone()
                if member is None:
                    id_member = db.execute('''INSERT INTO members(source,club_key,external_id,name,rating,gender)
                        VALUES(?,?,?,?,?,?)''', (source,club_key,player['external'],player['name'],1200 if player['rating'] is None else player['rating'],player['gender'])).lastrowid
                    member = db.execute('SELECT * FROM members WHERE id=?', (id_member,)).fetchone()
                else:
                    id_member = member['id']
                    if player['gender'] is None:
                        db.execute('UPDATE members SET name=? WHERE id=?', (player['name'],id_member))
                    else:
                        db.execute('UPDATE members SET name=?,gender=? WHERE id=?', (player['name'],player['gender'],id_member))
                old = db.execute('SELECT * FROM roster WHERE id_session=? AND id_member=?', (id_session,id_member)).fetchone()
                if old and old['queue_state'] in ('assigned', 'playing') and (
                        (player['gender'] is not None and player['gender'] != member['gender']) or
                        (player['group'] is not None and player['group'] != old['club_group'])):
                    raise Problem('Resolve the active game before changing player categories or groups.', 409)
                if old:
                    db.execute('''UPDATE roster SET rsvp='yes',club_group=COALESCE(?,club_group)
                        WHERE id=?''', (player['group'],old['id']))
                    id_roster = old['id']
                else:
                    id_roster = db.execute('''INSERT INTO roster(id_session,id_member,rsvp,membership,waiver,
                        base_rating,base_deviation,base_volatility,club_group)
                        VALUES(?,?,'yes','unknown','unknown',?,?,?,?)''',
                        (id_session,id_member,member['rating'],member['deviation'],member['volatility'],player['group'])).lastrowid
                roster_by_external[player['external']] = id_roster
            for first, second in validated_pairs:
                id_a,id_b=sorted((roster_by_external[first],roster_by_external[second]))
                existing = db.execute('''SELECT id_player_a,id_player_b FROM team_pairs
                    WHERE id_session=? AND (id_player_a IN (?,?) OR id_player_b IN (?,?))''',
                    (id_session,id_a,id_b,id_a,id_b)).fetchone()
                if existing and (existing['id_player_a'],existing['id_player_b']) != (id_a,id_b):
                    raise Problem('One of these players already has another partner. Unpair them first.', 409)
                if not existing:
                    if db.execute("SELECT 1 FROM roster WHERE id IN (?,?) AND queue_state IN ('assigned','playing')",
                                  (id_a,id_b)).fetchone():
                        raise Problem('Resolve active games before changing a pair.', 409)
                    db.execute('INSERT INTO team_pairs(id_session,id_player_a,id_player_b,created_at) VALUES(?,?,?,?)',
                               (id_session,id_a,id_b,self.clock()))
            self.audit(db,id_session,'roster.reviewed_imported',{'source':source,'rows':len(validated),'pairs':len(validated_pairs)})
        return len(validated)

    def checkin_all(self, id_session, revision):
        with self.transaction(id_session, revision) as (db, session):
            absent = db.execute("SELECT r.*,m.rating,m.deviation,m.volatility FROM roster r JOIN members m ON m.id=r.id_member WHERE r.id_session=? AND r.rsvp='yes' AND r.attendance IN ('absent','no_show') ORDER BY r.id", (id_session,)).fetchall()
            present = db.execute("SELECT COUNT(*) FROM roster WHERE id_session=? AND attendance='present'", (id_session,)).fetchone()[0]
            candidates=[]
            for player in absent:
                other=db.execute('''SELECT 1 FROM roster r JOIN sessions s ON s.id=r.id_session
                    WHERE r.id_member=? AND r.id_session!=? AND s.status='active'
                    AND (r.attendance='present' OR r.games_played>0)''',(player['id_member'],id_session)).fetchone()
                if not other:candidates.append(player)
            if present + len(candidates) > session['max_players']:
                raise Problem('There are more absent players than the remaining session capacity.',409)
            now=self.clock()
            added=0
            for player in candidates:
                db.execute('''UPDATE roster SET attendance='present',checked_in_at=?,checked_out_at=NULL,is_late=?,
                    base_rating=?,base_deviation=?,base_volatility=? WHERE id=?''',
                    (now,now>session['starts_at']+15*60,player['base_rating'] if player['games_played'] else player['rating'],
                     player['base_deviation'] if player['games_played'] else player['deviation'],
                     player['base_volatility'] if player['games_played'] else player['volatility'],player['id']))
                if player['membership']=='active' and player['waiver']=='valid':
                    self.enqueue(db,id_session,player['id'])
                added+=1
            self.audit(db,id_session,'players.checked_in_all',{'players':added})
        return added

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

    def pair_players(self, id_session, revision, id_a, id_b):
        if type(id_a) is not int or type(id_b) is not int or id_a == id_b:
            raise Problem('Choose two different players to pair.')
        with self.transaction(id_session, revision) as (db, _session):
            players = db.execute('SELECT id,queue_state FROM roster WHERE id_session=? AND id IN (?,?)',
                                 (id_session, id_a, id_b)).fetchall()
            if len(players) != 2:
                raise Problem('Both players must be on this session roster.', 404)
            if any(p['queue_state'] in ('assigned','playing') for p in players):
                raise Problem('Resolve active court assignments before changing a pair.', 409)
            occupied = db.execute('''SELECT 1 FROM team_pairs
                WHERE id_session=? AND (id_player_a IN (?,?) OR id_player_b IN (?,?))''',
                (id_session, id_a, id_b, id_a, id_b)).fetchone()
            if occupied:
                raise Problem('A selected player already has a partner. Unpair them first.', 409)
            a, b = sorted((id_a, id_b))
            db.execute('INSERT INTO team_pairs(id_session,id_player_a,id_player_b,created_at) VALUES(?,?,?,?)',
                       (id_session, a, b, self.clock()))
            self.audit(db, id_session, 'players.paired', {'players': [a, b]})

    def unpair_player(self, id_session, revision, id_roster):
        if type(id_roster) is not int:
            raise Problem('Invalid player ID.')
        with self.transaction(id_session, revision) as (db, _session):
            player = db.execute('SELECT id,queue_state FROM roster WHERE id=? AND id_session=?',
                                 (id_roster, id_session)).fetchone()
            if not player:
                raise Problem('Player not found.', 404)
            if player['queue_state'] in ('assigned','playing'):
                raise Problem('Resolve active court assignments before changing a pair.', 409)
            pair = db.execute('''SELECT id_player_a,id_player_b FROM team_pairs
                WHERE id_session=? AND (id_player_a=? OR id_player_b=?)''',
                (id_session, id_roster, id_roster)).fetchone()
            if not pair:
                raise Problem('This player is not paired.', 409)
            db.execute('DELETE FROM team_pairs WHERE id_session=? AND id_player_a=? AND id_player_b=?',
                       (id_session, pair['id_player_a'], pair['id_player_b']))
            self.audit(db, id_session, 'players.unpaired', {'players': [pair['id_player_a'], pair['id_player_b']]})

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
        with self.transaction(id_session, revision) as (db, session):
            return self.assign_courts(db, session, range(1, session['court_count']+1))

    def assign_courts(self, db, session, courts, id_rebuild=None, excluded_teams=None):
        id_session = session['id']
        assigned, reasons = [], []
        used = {g[0] for g in db.execute("SELECT court FROM games WHERE id_session=? AND status IN ('assigned','playing')", (id_session,))}
        if not id_rebuild and session['mode']=='social_mix' and db.execute("SELECT 1 FROM games WHERE id_session=? AND status='assigned' LIMIT 1", (id_session,)).fetchone():
            return {'assigned': [], 'messages': ['Social Mix: start the planned match before building the next mix.']}
        partners, opponents = self.histories(db, id_session)
        pair_map = {}
        for pair in db.execute('SELECT id_player_a,id_player_b FROM team_pairs WHERE id_session=?', (id_session,)):
            pair_map[pair['id_player_a']] = pair['id_player_b']
            pair_map[pair['id_player_b']] = pair['id_player_a']
        outcomes, last_courts = {}, {}
        for row in db.execute('''SELECT g.id,g.court,g.score_a,g.score_b,gp.id_roster,gp.side FROM games g
            JOIN game_players gp ON gp.id_game=g.id WHERE g.id_session=? AND g.status='completed'
            ORDER BY g.id DESC''', (id_session,)):
            if row['id_roster'] in outcomes:
                continue
            outcomes[row['id_roster']] = 'winner' if ((row['score_a'] > row['score_b']) == (row['side'] == 'a')) else 'loser'
            last_courts[row['id_roster']] = row['court']
        used_bands = set()
        if session['mode'] == 'skill_courts':
            active_bands = {}
            for row in db.execute('''SELECT g.id,m.rating FROM games g
                JOIN game_players gp ON gp.id_game=g.id
                JOIN roster r ON r.id=gp.id_roster
                JOIN members m ON m.id=r.id_member
                WHERE g.id_session=? AND g.status IN ('assigned','playing')''', (id_session,)):
                active_bands.setdefault(row['id'],set()).add(skill_band(row['rating']))
            used_bands = {next(iter(values)) for values in active_bands.values() if len(values)==1}
        for court in courts:
            if court in used and not id_rebuild:
                continue
            players = [dict(p) for p in db.execute('''SELECT r.id,r.ticket,r.games_played,r.club_group,m.rating,m.rated_games,m.gender FROM roster r
                JOIN members m ON m.id=r.id_member WHERE r.id_session=? AND r.attendance='present'
                AND r.queue_state='waiting' AND r.membership='active' AND r.waiver='valid' ORDER BY r.ticket,r.id''', (id_session,))]
            for player in players:
                player['paired_with'] = pair_map.get(player['id'])
                player['outcome'] = outcomes.get(player['id'])
                last_court = last_courts.get(player['id'])
                player['target_court'] = (max(1,last_court-1) if player['outcome']=='winner' else
                                          min(session['court_count'],last_court+1) if player['outcome']=='loser' else None)
            mode = session['mode']
            candidate_sets = []
            band = None
            if mode in ('skill_separated','skill_courts'):
                bands = ('Beginner','Intermediate','Advanced','Competitive')
                by_band = {name:[p for p in players if skill_band(p['rating'])==name] for name in bands}
                if mode == 'skill_separated':
                    anchor_band = skill_band(players[0]['rating']) if players else None
                    candidate_sets = [(by_band.get(anchor_band, []), 'balanced')]
                else:
                    available = [name for name in bands if len(by_band[name]) >= 4]
                    unassigned = [name for name in available if name not in used_bands]
                    band = max(unassigned or available, key=lambda name:len(by_band[name]), default=None)
                    candidate_sets = [(by_band.get(band, []), 'balanced')] if band else []
            elif mode == 'winners_losers':
                anchor_outcome = players[0].get('outcome') if players else None
                if anchor_outcome:
                    outcomes_to_try = (anchor_outcome,)
                elif not outcomes:
                    outcomes_to_try = ('neutral',)
                else:
                    outcomes_to_try = ('winner','loser')
                neutral = [p for p in players if p.get('outcome') is None]
                candidate_sets = [([p for p in players if p.get('outcome')==result] + neutral, 'balanced')
                                  for result in outcomes_to_try]
                candidate_sets = [(pool, objective) for pool,objective in candidate_sets if len(pool)>=4]
            elif mode == 'king_queen':
                targeted = [p for p in players if p['target_court']==court]
                neutral = [p for p in players if p['target_court'] is None]
                candidate_sets = [(targeted+neutral if targeted else neutral, 'balanced')]
            elif mode == 'club_wars':
                anchor_group = players[0].get('club_group') if players else None
                groups = sorted({p.get('club_group') for p in players if p.get('club_group')})
                if anchor_group:
                    for group in groups:
                        if group != anchor_group:
                            continue
                        for opponent_group in (value for value in groups if value != group):
                            candidate_sets.append(([p for p in players if p.get('club_group') in (group,opponent_group)], 'club_wars'))
            else:
                candidate_sets = [(players, mode)]
            candidates = []
            for pool, objective in candidate_sets:
                match = choose_game(pool, partners, opponents, mode=objective, excluded_teams=excluded_teams)
                if match is not None:
                    candidates.append(match)
            match = min(candidates, key=lambda item:item['key']) if candidates else None
            if match is None:
                if mode == 'mixed_doubles':
                    detail = 'needs two players who self-identified as men and two as women.'
                elif mode == 'club_wars':
                    groups = {p.get('club_group') for p in players if p.get('club_group')}
                    detail = ('needs every player assigned to Group A or Group B.' if any(not p.get('club_group') for p in players) or len(groups)<2
                              else 'has no valid team split with the current partner preferences.')
                elif mode in ('skill_courts','skill_separated'):
                    detail = 'needs four checked-in players in the same skill band.'
                elif mode == 'winners_losers':
                    detail = 'needs four available players from a winners or losers group.'
                elif mode == 'king_queen':
                    detail = 'needs four players at this court level.'
                else:
                    detail = 'needs four eligible players.'
                reasons.append(f'Court {court}: {detail}' if len(players) >= 4 else f'Court {court}: need four eligible players.')
                break
            team_a, team_b = match['teams']
            mean_a, mean_b = (sum(p['rating'] for p in t) / 2 for t in match['teams'])
            reason = {'social_mix':'Social Mix: rotates partners first and avoids recent opponent repeats; ratings are not used.',
                      'skill_separated':f'Skill Separated: {skill_band(team_a[0]["rating"])} players only.',
                      'winners_losers':'Winners / Losers: same recent-result group, with newcomers allowed to join.',
                      'mixed_doubles':'Mixed Doubles: one self-identified man and woman on each team.',
                      'club_wars':'Club Wars: each team represents one player group.',
                      'king_queen':f'King/Queen: court {court} promotion and demotion rotation.'}.get(mode,
                      f'Skill Courts: {band} group.' if mode=='skill_courts' else match['reason'])
            if id_rebuild:
                id_game = id_rebuild
                db.execute('''UPDATE games SET assigned_at=?,mean_a=?,mean_b=?,expected_a=?,cost=?,reason=? WHERE id=?''',
                           (self.clock(), mean_a, mean_b, match['expected'], match['cost'], reason, id_game))
            else:
                id_game = db.execute('''INSERT INTO games(id_session,court,assigned_at,mean_a,mean_b,expected_a,cost,reason)
                    VALUES(?,?,?,?,?,?,?,?)''', (id_session, court, self.clock(), mean_a, mean_b, match['expected'], match['cost'], reason)).lastrowid
            for side, team in (('a', team_a), ('b', team_b)):
                for p in team:
                    member = db.execute('''SELECT m.* FROM members m JOIN roster r ON r.id_member=m.id WHERE r.id=?''', (p['id'],)).fetchone()
                    db.execute('INSERT INTO active_assignments(id_roster,id_game) VALUES(?,?)', (p['id'], id_game))
                    db.execute('INSERT INTO game_players(id_game,id_roster,side,rating,deviation,volatility) VALUES(?,?,?,?,?,?)',
                               (id_game, p['id'], side, member['rating'], member['deviation'], member['volatility']))
                    db.execute("UPDATE roster SET queue_state='assigned' WHERE id=?", (p['id'],))
            assigned.append(id_game)
            if band:
                used_bands.add(band)
            if mode == 'social_mix':
                break
        if assigned and not id_rebuild:
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
            elif action == 'swap_winner':
                if game['status'] != 'completed':
                    raise Problem('Only completed games have a winner to correct.', 409)
                db.execute('UPDATE games SET score_a=?,score_b=? WHERE id=?',
                           (game['score_b'], game['score_a'], id_game))
                self.audit(db, id_session, 'game.winner_swapped', {
                    'id_game': id_game, 'before': [game['score_a'], game['score_b']],
                    'after': [game['score_b'], game['score_a']]})
            elif action == 'rebuild':
                if game['status'] != 'assigned':
                    raise Problem('Only an unstarted Up Next game can be rebuilt.', 409)
                old_teams = [tuple(row['id_roster'] for row in db.execute(
                    'SELECT id_roster FROM game_players WHERE id_game=? AND side=? ORDER BY id_roster',
                    (id_game, side))) for side in ('a', 'b')]
                db.execute('DELETE FROM active_assignments WHERE id_game=?', (id_game,))
                db.execute('DELETE FROM game_players WHERE id_game=?', (id_game,))
                db.execute("UPDATE roster SET queue_state='waiting' WHERE id IN (?,?,?,?)",
                           tuple(p['id'] for p in players))
                result = self.assign_courts(db, session, [game['court']], id_game, old_teams)
                if not result['assigned']:
                    raise Problem('No alternative valid matchup available. The existing Up Next plan was kept.', 409)
                self.audit(db, id_session, 'game.rebuilt', {'id_game': id_game, 'previous_teams': old_teams})
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
            if action not in ('cancel', 'swap_winner', 'rebuild'):
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
