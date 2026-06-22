import { useState, useEffect } from 'react';
import TrackingMap from '../components/Map';
import DeviceList from '../components/DeviceList';
import GeofenceEditor from '../components/GeofenceEditor';
import { useSocket } from '../hooks/useSocket';
import { apiFetch } from '../utils/api';

export default function Dashboard() {
  const [devices, setDevices] = useState([]);
  const [geofences, setGeofences] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [tab, setTab] = useState('devices');
  const [error, setError] = useState('');
  const { connected, positions, geofenceEvents } = useSocket();

  useEffect(() => {
    apiFetch('/devices').then(setDevices).catch(err => setError(err.message));
    apiFetch('/geofences').then(setGeofences).catch(err => setError(err.message));
  }, []);

  return (
    <div className="dashboard">
      <div className="sidebar">
        <div className="sidebar-header">
          <h2>WatcherV1</h2>
          <span className={`conn-status ${connected ? 'online' : 'offline'}`}>
            {connected ? 'Live' : 'Offline'}
          </span>
        </div>

        {error && <p className="error" style={{ padding: '0 1rem', color: '#ef4444' }}>{error}</p>}

        <div className="tab-bar">
          <button className={tab === 'devices' ? 'active' : ''} onClick={() => setTab('devices')}>Devices</button>
          <button className={tab === 'geofences' ? 'active' : ''} onClick={() => setTab('geofences')}>Geofences</button>
          <button className={tab === 'events' ? 'active' : ''} onClick={() => setTab('events')}>Events</button>
        </div>

        {tab === 'devices' && (
          <DeviceList
            devices={devices}
            setDevices={setDevices}
            positions={positions}
            onSelect={setSelectedDevice}
          />
        )}

        {tab === 'geofences' && (
          <GeofenceEditor geofences={geofences} setGeofences={setGeofences} />
        )}

        {tab === 'events' && (
          <div className="events-list">
            <h3>Geofence Events</h3>
            {geofenceEvents.length === 0 && <p className="empty">No events yet</p>}
            <ul>
              {geofenceEvents.map((evt, i) => (
                <li key={i} className={`event-item ${evt.event}`}>
                  <strong>{evt.geofence}</strong>
                  <span>Device {evt.device_id} {evt.event}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <a href="/history" className="history-link" style={{ display: 'block', textAlign: 'center', color: '#3b82f6', padding: '0.5rem', fontSize: '0.9rem', textDecoration: 'none' }}>
          Route History
        </a>
        <button className="logout-btn" onClick={() => { localStorage.clear(); window.location.reload(); }}>
          Logout
        </button>
      </div>

      <div className="map-container">
        <TrackingMap
          positions={positions}
          geofences={geofences}
          selectedDevice={selectedDevice}
        />
      </div>
    </div>
  );
}
