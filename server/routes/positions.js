const express = require('express');
const Position = require('../models/position');
const Device = require('../models/device');
const { authenticate } = require('../middleware/auth');

const router = express.Router();

router.post('/report', (req, res) => {
  const { device_id, unique_id, latitude, longitude, altitude, speed, heading, accuracy, timestamp } = req.body;

  let device;
  if (unique_id) {
    device = Device.findByUniqueId(unique_id);
  } else if (device_id) {
    device = Device.findById(device_id);
  }
  if (!device) return res.status(404).json({ error: 'Device not found' });

  const position = Position.create(device.id, { latitude, longitude, altitude, speed, heading, accuracy, timestamp });
  Device.update(device.id, { status: 'active', last_seen: new Date().toISOString() });

  const io = req.app.get('io');
  if (io) {
    io.emit('position:update', { device_id: device.id, device_name: device.name, ...position });
  }

  res.status(201).json(position);
});

router.use(authenticate);

router.get('/latest', (req, res) => {
  const positions = Position.getLatestAll();
  res.json(positions);
});

router.get('/latest/:deviceId', (req, res) => {
  const position = Position.getLatestByDevice(req.params.deviceId);
  if (!position) return res.status(404).json({ error: 'No positions found' });
  res.json(position);
});

router.get('/history/:deviceId', (req, res) => {
  const { from, to, limit } = req.query;
  if (!from || !to) {
    return res.status(400).json({ error: 'from and to query params required (ISO 8601)' });
  }
  const positions = Position.getHistory(
    req.params.deviceId, from, to, parseInt(limit) || 1000
  );
  res.json(positions);
});

module.exports = router;
