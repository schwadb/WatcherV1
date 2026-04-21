const jwt = require('jsonwebtoken');
const { JWT_SECRET } = require('../middleware/auth');
const Position = require('../models/position');
const Device = require('../models/device');
const { checkGeofences } = require('./geofence');

function initializeSocket(io) {
  io.use((socket, next) => {
    const token = socket.handshake.auth?.token;
    if (!token) return next(new Error('Authentication required'));
    try {
      socket.user = jwt.verify(token, JWT_SECRET);
      next();
    } catch {
      next(new Error('Invalid token'));
    }
  });

  io.on('connection', (socket) => {
    console.log(`Client connected: ${socket.user.username}`);

    socket.on('position:report', (data) => {
      const { device_id, unique_id, latitude, longitude, altitude, speed, heading, accuracy } = data;

      let device;
      if (unique_id) device = Device.findByUniqueId(unique_id);
      else if (device_id) device = Device.findById(device_id);
      if (!device) return socket.emit('error', { message: 'Device not found' });

      const position = Position.create(device.id, {
        latitude, longitude, altitude, speed, heading, accuracy,
        timestamp: new Date().toISOString()
      });

      Device.update(device.id, { status: 'active', last_seen: new Date().toISOString() });
      io.emit('position:update', { device_id: device.id, device_name: device.name, ...position });
      checkGeofences(device.id, latitude, longitude, io);
    });

    socket.on('disconnect', () => {
      console.log(`Client disconnected: ${socket.user.username}`);
    });
  });
}

module.exports = { initializeSocket };
