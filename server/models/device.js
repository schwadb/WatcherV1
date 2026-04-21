const db = require('./db');

const Device = {
  create(name, uniqueId, type, userId) {
    const stmt = db.prepare(
      'INSERT INTO devices (name, unique_id, type, user_id) VALUES (?, ?, ?, ?)'
    );
    const result = stmt.run(name, uniqueId, type, userId);
    return this.findById(result.lastInsertRowid);
  },

  findById(id) {
    return db.prepare('SELECT * FROM devices WHERE id = ?').get(id);
  },

  findByUniqueId(uniqueId) {
    return db.prepare('SELECT * FROM devices WHERE unique_id = ?').get(uniqueId);
  },

  findByUser(userId) {
    return db.prepare('SELECT * FROM devices WHERE user_id = ?').all(userId);
  },

  findAll() {
    return db.prepare('SELECT * FROM devices').all();
  },

  update(id, fields) {
    const allowed = ['name', 'type', 'status', 'last_seen'];
    const updates = [];
    const values = [];
    for (const [key, val] of Object.entries(fields)) {
      if (allowed.includes(key)) {
        updates.push(`${key} = ?`);
        values.push(val);
      }
    }
    if (updates.length === 0) return this.findById(id);
    values.push(id);
    db.prepare(`UPDATE devices SET ${updates.join(', ')} WHERE id = ?`).run(...values);
    return this.findById(id);
  },

  delete(id) {
    return db.prepare('DELETE FROM devices WHERE id = ?').run(id);
  }
};

module.exports = Device;
