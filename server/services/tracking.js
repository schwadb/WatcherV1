const jwt = require('jsonwebtoken');
const { JWT_SECRET } = require('../middleware/auth');
const Position = require('../models/position');
const Device = require('../models/device');
const { checkGeofences } = require('./geofence');
const logger = require('../logger');

const socketRateMap = new Map();
const SOCKET_RATE_WINDOW = 1000;
const SOCKET_RATE_MAX = 10;

function isRateLimited(socketId) {
  const now = Date.now();
  const entry = socketRateMap.get(socketId);
  if (!entry || now - entry.windowStart > SOCKET_RATE_WINDOW) {
    socketRateMap.set(socketId, { windowStart: now, count: 1 });
    return false;
  }
  entry.count++;
  return entry.count > SOCKET_RATE_MAX;
}

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
    logger.info({ user: socket.user.username }, 'Client connected');

    socket.join(`user:${socket.user.id}`);

    if (socket.user.role === 'admin') {
      socket.join('admins');
    }

    socket.on('position:report', (data) => {
      if (isRateLimited(socket.id)) {
        return socket.emit('error', { message: 'Rate limit exceeded' });
      }

      const { device_id, unique_id, latitude, longitude, altitude, speed, heading, accuracy } = data;

      if (typeof latitude !== 'number' || latitude < -90 || latitude > 90 ||
          typeof longitude !== 'number' || longitude < -180 || longitude > 180) {
        return socket.emit('error', { message: 'Invalid coordinates' });
      }

      let device;
      if (unique_id) device = Device.findByUniqueId(unique_id);
      else if (device_id) device = Device.findById(device_id);
      if (!device) return socket.emit('error', { message: 'Device not found' });

      const position = Position.create(device.id, {
        latitude, longitude, altitude, speed, heading, accuracy,
        timestamp: new Date().toISOString()
      });

      Device.update(device.id, { status: 'active', last_seen: new Date().toISOString() });

      const update = { device_id: device.id, device_name: device.name, ...position };
      io.to(`user:${device.user_id}`).emit('position:update', update);
      io.to('admins').emit('position:update', update);

      checkGeofences(device.id, latitude, longitude, io);
    });

    socket.on('disconnect', () => {
      socketRateMap.delete(socket.id);
      logger.info({ user: socket.user.username }, 'Client disconnected');
    });
  });
}

module.exports = { initializeSocket };
