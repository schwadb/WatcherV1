import { useState, useEffect } from 'react';
import TrackingMap from '../components/Map';
import TrackPlayer from '../components/TrackPlayer';

const API = '/api';
function apiFetch(path) {
  const token = localStorage.getItem('token');
  return fetch(API + path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

export default function History() {
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [track, setTrack] = useState([]);
  const [positions, setPositions] = useState({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    apiFetch('/devices').then(setDevices).catch(() => {});
    const now = new Date();
    const dayAgo = new Date(now.getTime() - 86400000);
    setTo(now.toISOString().slice(0, 16));
    setFrom(dayAgo.toISOString().slice(0, 16));
  }, []);

  async function loadHistory() {
    if (!deviceId || !from || !to) return;
    setLoading(true);
    try {
      const data = await apiFetch(
        `/positions/history/${deviceId}?from=${new Date(from).toISOString()}&to=${new Date(to).toISOString()}`
      );
      setTrack(data);
      if (data.length > 0) {
        setPositions({ [deviceId]: data[data.length - 1] });
      }
    } catch {
      setTrack([]);
    }
    setLoading(false);
  }

  function onPositionChange(index) {
    if (track[index]) {
      setPositions({ [deviceId]: track[index] });
    }
  }

  return (
    <div className="dashboard">
      <div className="sidebar">
        <div className="sidebar-header">
          <h2>Route History</h2>
          <a href="/" className="back-link">Back to Live</a>
        </div>

        <div className="history-form">
          <select value={deviceId} onChange={e => setDeviceId(e.target.value)}>
            <option value="">Select device</option>
            {devices.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <label>From</label>
          <input type="datetime-local" value={from} onChange={e => setFrom(e.target.value)} />
          <label>To</label>
          <input type="datetime-local" value={to} onChange={e => setTo(e.target.value)} />
          <button onClick={loadHistory} disabled={loading}>
            {loading ? 'Loading...' : 'Load History'}
          </button>
        </div>

        {track.length > 0 && (
          <>
            <p className="track-count">{track.length} points loaded</p>
            <TrackPlayer track={track} onPositionChange={onPositionChange} />
          </>
        )}
      </div>

      <div className="map-container">
        <TrackingMap positions={positions} track={track} />
      </div>
    </div>
  );
}
