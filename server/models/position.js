const db = require('./db');

const Position = {
  create(deviceId, data) {
    const stmt = db.prepare(
      `INSERT INTO positions (device_id, latitude, longitude, altitude, speed, heading, accuracy, timestamp)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    );
    const result = stmt.run(
      deviceId, data.latitude, data.longitude,
      data.altitude ?? null, data.speed ?? null,
      data.heading ?? null, data.accuracy ?? null,
      data.timestamp || new Date().toISOString()
    );
    return this.findById(result.lastInsertRowid);
  },

  findById(id) {
    return db.prepare('SELECT * FROM positions WHERE id = ?').get(id);
  },

  getLatestByDevice(deviceId) {
    return db.prepare(
      'SELECT * FROM positions WHERE device_id = ? ORDER BY timestamp DESC LIMIT 1'
    ).get(deviceId);
  },

  getLatestAll() {
    return db.prepare(`
      SELECT p.*, d.name as device_name FROM positions p
      INNER JOIN (
        SELECT device_id, MAX(id) as max_id
        FROM positions GROUP BY device_id
      ) latest ON p.id = latest.max_id
      JOIN devices d ON p.device_id = d.id
    `).all();
  },

  getHistory(deviceId, from, to, limit = 1000) {
    return db.prepare(
      `SELECT * FROM positions
       WHERE device_id = ? AND timestamp BETWEEN ? AND ?
       ORDER BY timestamp ASC LIMIT ?`
    ).all(deviceId, from, to, limit);
  },

  deleteOlderThan(days) {
    const cutoff = new Date(Date.now() - days * 86400000).toISOString();
    return db.prepare('DELETE FROM positions WHERE created_at < ?').run(cutoff);
  },

  getCount() {
    return db.prepare('SELECT COUNT(*) as count FROM positions').get().count;
  }
};

module.exports = Position;
