import { useEffect, useRef, useState } from 'react';
import { io } from 'socket.io-client';

export function useSocket() {
  const socketRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [positions, setPositions] = useState({});
  const [geofenceEvents, setGeofenceEvents] = useState([]);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) return;

    const socket = io(window.location.origin, { auth: { token } });
    socketRef.current = socket;

    socket.on('connect', () => setConnected(true));
    socket.on('disconnect', () => setConnected(false));

    socket.on('position:update', (data) => {
      setPositions(prev => ({ ...prev, [data.device_id]: data }));
    });

    socket.on('geofence:event', (event) => {
      setGeofenceEvents(prev => [event, ...prev].slice(0, 50));
    });

    return () => socket.disconnect();
  }, []);

  return { socket: socketRef.current, connected, positions, geofenceEvents };
}
