# WatcherV1

Open source GPS tracking application.

## Tech Stack
- **Server**: Node.js, Express, Socket.io, SQLite (better-sqlite3), JWT auth
- **Client**: React 18, Vite, Leaflet/OpenStreetMap, Socket.io-client, React Router

## Project Structure
- `server/` — Express API + WebSocket server
- `client/` — React SPA (Vite)
- Root has Docker/compose for deployment

## Commands
- Server: `cd server && npm install && npm run dev`
- Client: `cd client && npm install && npm run dev`
- Docker: `docker compose up --build`

## Architecture
- REST API at `/api/*` with JWT Bearer auth
- WebSocket (Socket.io) for real-time position updates
- SQLite database with WAL mode, stored at `server/watcher.db`
- Client proxies `/api` and `/socket.io` to server in dev mode

## Key Patterns
- Device position reporting via `POST /api/positions/report` (auth via X-API-Key header or Bearer token; open if DEVICE_API_KEY env var is not set)
- All other endpoints require JWT
- Geofence checks run on every position update with bounding-box pre-filtering, emit scoped Socket.io events
- Admin role can see all devices; viewer role sees only own devices
- Devices auto-marked inactive after 5 minutes without updates (configurable via STALE_DEVICE_MS env var)
- Graceful shutdown on SIGTERM/SIGINT

## Environment Variables
- `JWT_SECRET` — Required, server will not start without it
- `DEVICE_API_KEY` — Optional, if set, position report endpoint requires this key or a valid JWT
- `STALE_DEVICE_MS` — Optional, milliseconds before marking device inactive (default: 300000 / 5 min)
- `DB_PATH` — Optional, SQLite database file path (default: server/watcher.db)
- `CLIENT_URL` — Optional, CORS origin (default: http://localhost:5173)
- `PORT` — Optional, server port (default: 3000)
