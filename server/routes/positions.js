const express = require('express');
const Position = require('../models/position');
const Device = require('../models/device');
const { authenticate } = require('../middleware/auth');
const { validatePositionData } = require('../middleware/validate');
const rateLimit = require('express-rate-limit');

const router = express.Router();

const reportLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 120,
  standardHeaders: true,
  legacyHeaders: false,
});

function authenticateReport(req, res, next) {
  const apiKey = req.headers['x-api-key'];
  const authHeader = req.headers.authorization;
  if (apiKey && process.env.DEVICE_API_KEY && apiKey === process.env.DEVICE_API_KEY) {
    return next();
  }
  if (authHeader && authHeader.startsWith('Bearer ')) {
    const jwt = require('jsonwebtoken');
    try {
      req.user = jwt.verify(authHeader.slice(7), process.env.JWT_SECRET);
      return next();
    } catch {
      return res.status(401).json({ error: 'Invalid token' });
    }
  }
  if (!process.env.DEVICE_API_KEY) {
    return next();
  }
  return res.status(401).json({ error: 'Authentication required: provide X-API-Key header or Bearer token' });
}

router.post('/report', reportLimiter, authenticateReport, validatePositionData, (req, res) => {
  const { device_id, unique_id, latitude, longitude, altitude, speed, heading, accuracy, timestamp } = req.body;

  let device;
  if (unique_id) {
    device = Device.findByUniqueId(unique_id);
  } else if (device_id) {
    device = Device.findById(device_id);
  }
  if (!device) return res.status(404).json({ error: 'Device not found' });

  if (req.user && req.user.role !== 'admin' && device.user_id !== req.user.id) {
    return res.status(403).json({ error: 'Access denied' });
  }

  const position = Position.create(device.id, { latitude, longitude, altitude, speed, heading, accuracy, timestamp });
  Device.update(device.id, { status: 'active', last_seen: new Date().toISOString() });

  const io = req.app.get('io');
  if (io) {
    io.to(`user:${device.user_id}`).emit('position:update', { device_id: device.id, device_name: device.name, ...position });
  }

  res.status(201).json(position);
});

router.use(authenticate);

router.get('/latest', (req, res) => {
  if (req.user.role === 'admin') {
    return res.json(Position.getLatestAll());
  }
  const devices = Device.findByUser(req.user.id);
  const deviceIds = new Set(devices.map(d => d.id));
  const positions = Position.getLatestAll().filter(p => deviceIds.has(p.device_id));
  res.json(positions);
});

router.get('/latest/:deviceId', (req, res) => {
  const deviceId = parseInt(req.params.deviceId);
  const device = Device.findById(deviceId);
  if (!device) return res.status(404).json({ error: 'Device not found' });
  if (req.user.role !== 'admin' && device.user_id !== req.user.id) {
    return res.status(403).json({ error: 'Access denied' });
  }
  const position = Position.getLatestByDevice(deviceId);
  if (!position) return res.status(404).json({ error: 'No positions found' });
  res.json(position);
});

router.get('/history/:deviceId', (req, res) => {
  const deviceId = parseInt(req.params.deviceId);
  const device = Device.findById(deviceId);
  if (!device) return res.status(404).json({ error: 'Device not found' });
  if (req.user.role !== 'admin' && device.user_id !== req.user.id) {
    return res.status(403).json({ error: 'Access denied' });
  }

  const { from, to, limit } = req.query;
  if (!from || !to) {
    return res.status(400).json({ error: 'from and to query params required (ISO 8601)' });
  }
  const positions = Position.getHistory(
    deviceId, from, to, parseInt(limit) || 1000
  );
  res.json(positions);
});

module.exports = router;
