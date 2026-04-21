const db = require('./db');
const bcrypt = require('bcryptjs');

const SALT_ROUNDS = 10;

const User = {
  create(username, email, password, role = 'viewer') {
    const hash = bcrypt.hashSync(password, SALT_ROUNDS);
    const stmt = db.prepare(
      'INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)'
    );
    const result = stmt.run(username, email, hash, role);
    return { id: result.lastInsertRowid, username, email, role };
  },

  findByUsername(username) {
    return db.prepare('SELECT * FROM users WHERE username = ?').get(username);
  },

  findById(id) {
    return db.prepare('SELECT id, username, email, role, created_at FROM users WHERE id = ?').get(id);
  },

  verifyPassword(plaintext, hash) {
    return bcrypt.compareSync(plaintext, hash);
  }
};

module.exports = User;
