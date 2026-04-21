const express = require('express');
const Device = require('../models/device');
const { authenticate, requireAdmin } = require('../middleware/auth');

const router = express.Router();

router.use(authenticate);

router.get('/', (req, res) => {
  const devices = req.user.role === 'admin'
    ? Device.findAll()
    : Device.findByUser(req.user.id);
  res.json(devices);
});

router.get('/:id', (req, res) => {
  const device = Device.findById(req.params.id);
  if (!device) return res.status(404).json({ error: 'Device not found' });
  if (req.user.role !== 'admin' && device.user_id !== req.user.id) {
    return res.status(403).json({ error: 'Access denied' });
  }
  res.json(device);
});

router.post('/', (req, res) => {
  const { name, unique_id, type } = req.body;
  if (!name || !unique_id) {
    return res.status(400).json({ error: 'name and unique_id required' });
  }
  try {
    const device = Device.create(name, unique_id, type || 'vehicle', req.user.id);
    res.status(201).json(device);
  } catch (err) {
    if (err.message.includes('UNIQUE')) {
      return res.status(409).json({ error: 'Device unique_id already exists' });
    }
    res.status(500).json({ error: 'Failed to create device' });
  }
});

router.put('/:id', (req, res) => {
  const device = Device.findById(req.params.id);
  if (!device) return res.status(404).json({ error: 'Device not found' });
  if (req.user.role !== 'admin' && device.user_id !== req.user.id) {
    return res.status(403).json({ error: 'Access denied' });
  }
  const updated = Device.update(req.params.id, req.body);
  res.json(updated);
});

router.delete('/:id', authenticate, requireAdmin, (req, res) => {
  const device = Device.findById(req.params.id);
  if (!device) return res.status(404).json({ error: 'Device not found' });
  Device.delete(req.params.id);
  res.json({ message: 'Device deleted' });
});

module.exports = router;
