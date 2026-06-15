const express = require('express');
const { createServer } = require('http');
const { Server } = require('socket.io');
const cors = require('cors');
const helmet = require('helmet');
const compression = require('compression');
const rateLimit = require('express-rate-limit');
const path = require('path');
const logger = require('./logger');

const authRoutes = require('./routes/auth');
const deviceRoutes = require('./routes/devices');
const positionRoutes = require('./routes/positions');
const geofenceRoutes = require('./routes/geofences');
const { initializeSocket } = require('./services/tracking');

const app = express();
const httpServer = createServer(app);

const allowedOrigin = process.env.CLIENT_URL || 'http://localhost:5173';
const io = new Server(httpServer, { cors: { origin: allowedOrigin } });

app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'", "'unsafe-inline'"],
      styleSrc: ["'self'", "'unsafe-inline'"],
      imgSrc: ["'self'", 'https://*.tile.openstreetmap.org', 'https://unpkg.com', 'data:'],
      connectSrc: ["'self'", 'ws:', 'wss:'],
    },
  },
}));
app.use(compression());
app.set('io', io);
app.use(cors({ origin: allowedOrigin }));
app.use(express.json({ limit: '1mb' }));

const apiLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 1000,
  standardHeaders: true,
  legacyHeaders: false,
});
app.use('/api/', apiLimiter);

const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 20,
  standardHeaders: true,
  legacyHeaders: false,
});
app.use('/api/auth/login', authLimiter);
app.use('/api/auth/register', authLimiter);

app.use('/api/auth', authRoutes);
app.use('/api/devices', deviceRoutes);
app.use('/api/positions', positionRoutes);
app.use('/api/geofences', geofenceRoutes);

app.get('/api/health', (req, res) => res.json({ status: 'ok', uptime: process.uptime() }));

const clientDist = path.join(__dirname, '..', 'client', 'dist');
app.use(express.static(clientDist));
app.get('*', (req, res) => {
  if (!req.path.startsWith('/api')) {
    res.sendFile(path.join(clientDist, 'index.html'));
  }
});

app.use((err, req, res, _next) => {
  logger.error({ err, method: req.method, url: req.url }, 'Unhandled error');
  res.status(err.status || 500).json({ error: 'Internal server error' });
});

initializeSocket(io);

const PORT = process.env.PORT || 3000;
httpServer.listen(PORT, () => logger.info({ port: PORT }, 'WatcherV1 server running'));
