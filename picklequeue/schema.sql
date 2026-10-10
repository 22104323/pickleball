PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  starts_at REAL NOT NULL,
  court_count INTEGER NOT NULL CHECK (court_count BETWEEN 1 AND 8),
  max_players INTEGER NOT NULL CHECK (max_players BETWEEN 4 AND 200),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','closed')),
  revision INTEGER NOT NULL DEFAULT 0,
  next_ticket INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS members (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL CHECK (source IN ('manual','reclub','demo')),
  club_key TEXT NOT NULL,
  external_id TEXT NOT NULL,
  name TEXT NOT NULL,
  rating REAL NOT NULL DEFAULT 1200 CHECK (rating BETWEEN 0 AND 4000),
  deviation REAL NOT NULL DEFAULT 350 CHECK (deviation > 0),
  volatility REAL NOT NULL DEFAULT 0.06 CHECK (volatility > 0),
  rated_games INTEGER NOT NULL DEFAULT 0,
  UNIQUE (source, club_key, external_id)
);
CREATE TABLE IF NOT EXISTS roster (
  id INTEGER PRIMARY KEY,
  id_session INTEGER NOT NULL REFERENCES sessions(id),
  id_member INTEGER NOT NULL REFERENCES members(id),
  rsvp TEXT NOT NULL CHECK (rsvp IN ('yes','no','waitlist','cancelled')),
  attendance TEXT NOT NULL DEFAULT 'absent' CHECK (attendance IN ('absent','present','left','no_show')),
  membership TEXT NOT NULL DEFAULT 'unknown' CHECK (membership IN ('active','expired','unknown')),
  waiver TEXT NOT NULL DEFAULT 'unknown' CHECK (waiver IN ('valid','missing','unknown')),
  queue_state TEXT NOT NULL DEFAULT 'off' CHECK (queue_state IN ('off','waiting','assigned','playing')),
  checked_in_at REAL,
  checked_out_at REAL,
  is_late INTEGER NOT NULL DEFAULT 0,
  ticket INTEGER,
  queued_at REAL,
  games_played INTEGER NOT NULL DEFAULT 0,
  base_rating REAL NOT NULL,
  base_deviation REAL NOT NULL,
  base_volatility REAL NOT NULL,
  UNIQUE (id_session, id_member)
);
CREATE TABLE IF NOT EXISTS games (
  id INTEGER PRIMARY KEY,
  id_session INTEGER NOT NULL REFERENCES sessions(id),
  court INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'assigned' CHECK (status IN ('assigned','playing','completed','cancelled')),
  assigned_at REAL NOT NULL,
  started_at REAL,
  completed_at REAL,
  score_a INTEGER,
  score_b INTEGER,
  mean_a REAL NOT NULL,
  mean_b REAL NOT NULL,
  expected_a REAL NOT NULL,
  cost REAL NOT NULL,
  reason TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_game_per_court ON games(id_session,court)
  WHERE status IN ('assigned','playing');
CREATE TABLE IF NOT EXISTS game_players (
  id_game INTEGER NOT NULL REFERENCES games(id),
  id_roster INTEGER NOT NULL REFERENCES roster(id),
  side TEXT NOT NULL CHECK (side IN ('a','b')),
  rating REAL NOT NULL,
  deviation REAL NOT NULL,
  volatility REAL NOT NULL,
  PRIMARY KEY (id_game,id_roster)
);
CREATE TABLE IF NOT EXISTS active_assignments (
  id_roster INTEGER PRIMARY KEY REFERENCES roster(id),
  id_game INTEGER NOT NULL REFERENCES games(id)
);
CREATE TABLE IF NOT EXISTS rating_history (
  id INTEGER PRIMARY KEY,
  id_session INTEGER NOT NULL REFERENCES sessions(id),
  id_member INTEGER NOT NULL REFERENCES members(id),
  old_rating REAL NOT NULL,
  new_rating REAL NOT NULL,
  old_deviation REAL NOT NULL,
  new_deviation REAL NOT NULL,
  old_volatility REAL NOT NULL,
  new_volatility REAL NOT NULL,
  UNIQUE (id_session,id_member)
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY,
  id_session INTEGER REFERENCES sessions(id),
  action TEXT NOT NULL,
  detail TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS roster_session ON roster(id_session,queue_state,ticket);
CREATE INDEX IF NOT EXISTS games_session ON games(id_session,status);
PRAGMA user_version = 1;
