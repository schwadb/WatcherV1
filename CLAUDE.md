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
- Device position reporting via `POST /api/positions/report` (no auth, for device firmware)
- All other endpoints require JWT
- Geofence checks run on every position update, emit Socket.io events
- Admin role can see all devices; viewer role sees only own devices
