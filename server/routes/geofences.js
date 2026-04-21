const express = require('express');
const db = require('../models/db');
const { authenticate } = require('../middleware/auth');

const router = express.Router();
router.use(authenticate);

router.get('/', (req, res) => {
  const geofences = req.user.role === 'admin'
    ? db.prepare('SELECT * FROM geofences').all()
    : db.prepare('SELECT * FROM geofences WHERE user_id = ?').all(req.user.id);
  res.json(geofences.map(g => ({
    ...g,
    coordinates: g.coordinates ? JSON.parse(g.coordinates) : null
  })));
});

router.post('/', (req, res) => {
  const { name, type, center_lat, center_lng, radius, coordinates } = req.body;
  if (!name) return res.status(400).json({ error: 'name required' });

  if (type === 'circle' && (!center_lat || !center_lng || !radius)) {
    return res.status(400).json({ error: 'Circle geofence needs center_lat, center_lng, radius' });
  }
  if (type === 'polygon' && !coordinates) {
    return res.status(400).json({ error: 'Polygon geofence needs coordinates array' });
  }

  const stmt = db.prepare(
    `INSERT INTO geofences (name, user_id, type, center_lat, center_lng, radius, coordinates)
     VALUES (?, ?, ?, ?, ?, ?, ?)`
  );
  const result = stmt.run(
    name, req.user.id, type || 'circle',
    center_lat || null, center_lng || null, radius || null,
    coordinates ? JSON.stringify(coordinates) : null
  );
  res.status(201).json({ id: result.lastInsertRowid, name, type: type || 'circle' });
});

router.delete('/:id', (req, res) => {
  const fence = db.prepare('SELECT * FROM geofences WHERE id = ?').get(req.params.id);
  if (!fence) return res.status(404).json({ error: 'Geofence not found' });
  if (req.user.role !== 'admin' && fence.user_id !== req.user.id) {
    return res.status(403).json({ error: 'Access denied' });
  }
  db.prepare('DELETE FROM geofences WHERE id = ?').run(req.params.id);
  res.json({ message: 'Geofence deleted' });
});

router.get('/events', (req, res) => {
  const events = db.prepare(`
    SELECT ge.*, g.name as geofence_name, d.name as device_name
    FROM geofence_events ge
    JOIN geofences g ON ge.geofence_id = g.id
    JOIN devices d ON ge.device_id = d.id
    ORDER BY ge.timestamp DESC LIMIT 100
  `).all();
  res.json(events);
});

module.exports = router;
