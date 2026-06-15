const Database = require('better-sqlite3');
const path = require('path');

const DB_PATH = process.env.DB_PATH || path.join(__dirname, '..', 'watcher.db');
const db = new Database(DB_PATH);

db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    unique_id TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL DEFAULT 'vehicle',
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'inactive',
    last_seen TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  );

  CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    altitude REAL,
    speed REAL,
    heading REAL,
    accuracy REAL,
    timestamp TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
  );

  CREATE INDEX IF NOT EXISTS idx_positions_device_ts ON positions(device_id, timestamp);

  CREATE TABLE IF NOT EXISTS geofences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL DEFAULT 'circle',
    center_lat REAL,
    center_lng REAL,
    radius REAL,
    coordinates TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  );

  CREATE TABLE IF NOT EXISTS geofence_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    geofence_id INTEGER NOT NULL,
    device_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (geofence_id) REFERENCES geofences(id) ON DELETE CASCADE,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
  );

  CREATE INDEX IF NOT EXISTS idx_geofence_events_ts ON geofence_events(timestamp DESC);
  CREATE INDEX IF NOT EXISTS idx_geofence_events_device ON geofence_events(device_id, timestamp DESC);
`);

module.exports = db;
