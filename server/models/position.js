const db = require('./db');

const Position = {
  create(deviceId, data) {
    const stmt = db.prepare(
      `INSERT INTO positions (device_id, latitude, longitude, altitude, speed, heading, accuracy, timestamp)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    );
    const result = stmt.run(
      deviceId, data.latitude, data.longitude,
      data.altitude || null, data.speed || null,
      data.heading || null, data.accuracy || null,
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
      SELECT p.* FROM positions p
      INNER JOIN (
        SELECT device_id, MAX(timestamp) as max_ts
        FROM positions GROUP BY device_id
      ) latest ON p.device_id = latest.device_id AND p.timestamp = latest.max_ts
    `).all();
  },

  getHistory(deviceId, from, to, limit = 1000) {
    return db.prepare(
      `SELECT * FROM positions
       WHERE device_id = ? AND timestamp BETWEEN ? AND ?
       ORDER BY timestamp ASC LIMIT ?`
    ).all(deviceId, from, to, limit);
  }
};

module.exports = Position;
