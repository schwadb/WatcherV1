import { useEffect, useRef, useState, useCallback } from 'react';
import { io } from 'socket.io-client';

export function useSocket() {
  const socketRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [positions, setPositions] = useState({});
  const [geofenceEvents, setGeofenceEvents] = useState([]);

  const loadInitialPositions = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/positions/latest', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        const posMap = {};
        for (const p of data) {
          posMap[p.device_id] = p;
        }
        setPositions(posMap);
      }
    } catch {
      // silent — socket will provide updates
    }
  }, []);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) return;

    const socket = io(window.location.origin, {
      auth: { token },
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 30000,
      reconnectionAttempts: Infinity,
    });
    socketRef.current = socket;

    socket.on('connect', () => {
      setConnected(true);
      loadInitialPositions();
    });
    socket.on('disconnect', () => setConnected(false));
    socket.on('connect_error', (err) => console.error('Socket connection error:', err.message));

    socket.on('position:update', (data) => {
      setPositions(prev => ({ ...prev, [data.device_id]: data }));
    });

    socket.on('geofence:event', (event) => {
      setGeofenceEvents(prev => [event, ...prev].slice(0, 50));
    });

    loadInitialPositions();

    return () => socket.disconnect();
  }, [loadInitialPositions]);

  return { socket: socketRef.current, connected, positions, geofenceEvents };
}
