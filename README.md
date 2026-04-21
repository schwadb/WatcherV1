# WatcherV1

Lightweight, self-hosted GPS tracking application. Real-time device monitoring with geofencing, route history, and a modern web dashboard.

## Features

- **Real-time tracking** — Live device positions via WebSocket
- **Interactive map** — Leaflet + OpenStreetMap (no API key required)
- **Device management** — CRUD for vehicles, people, and assets
- **Geofencing** — Circle/polygon zones with enter/exit alerts
- **Route history** — Historical track playback with timeline scrubber
- **Multi-user auth** — JWT-based with admin/viewer roles
- **REST API** — Full API for third-party integrations
- **Privacy-first** — Self-hosted, your data stays on your server
- **Mobile-ready** — Responsive design, works on any device
- **Docker support** — One-command deployment

## Quick Start

### Development

```bash
# Server
cd server
npm install
npm run dev

# Client (separate terminal)
cd client
npm install
npm run dev
```

Server runs on `http://localhost:3000`, client on `http://localhost:5173`.

### Docker

```bash
docker compose up --build
```

App available at `http://localhost:3000`.

## API

All endpoints (except position reporting and auth) require `Authorization: Bearer <token>`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Get JWT token |
| GET | `/api/auth/me` | Current user |
| GET | `/api/devices` | List devices |
| POST | `/api/devices` | Add device |
| PUT | `/api/devices/:id` | Update device |
| DELETE | `/api/devices/:id` | Delete device (admin) |
| POST | `/api/positions/report` | Report GPS position (device) |
| GET | `/api/positions/latest` | Latest positions |
| GET | `/api/positions/history/:id` | Route history |
| GET | `/api/geofences` | List geofences |
| POST | `/api/geofences` | Create geofence |
| DELETE | `/api/geofences/:id` | Delete geofence |
| GET | `/api/health` | Server health check |

### Report Position (from device/firmware)

```bash
curl -X POST http://localhost:3000/api/positions/report \
  -H "Content-Type: application/json" \
  -d '{"unique_id": "DEVICE001", "latitude": 40.7128, "longitude": -74.0060, "speed": 45.2}'
```

## Tech Stack

- **Backend**: Node.js, Express, Socket.io, better-sqlite3
- **Frontend**: React 18, Vite, Leaflet, React Router
- **Auth**: JWT + bcrypt
- **Database**: SQLite (WAL mode)

## License

MIT
