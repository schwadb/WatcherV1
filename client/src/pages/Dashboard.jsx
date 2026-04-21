import { useState, useEffect } from 'react';
import TrackingMap from '../components/Map';
import DeviceList from '../components/DeviceList';
import GeofenceEditor from '../components/GeofenceEditor';
import { useSocket } from '../hooks/useSocket';

const API = '/api';
function apiFetch(path) {
  const token = localStorage.getItem('token');
  return fetch(API + path, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}

export default function Dashboard() {
  const [devices, setDevices] = useState([]);
  const [geofences, setGeofences] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [tab, setTab] = useState('devices');
  const { connected, positions, geofenceEvents } = useSocket();

  useEffect(() => {
    apiFetch('/devices').then(setDevices).catch(() => {});
    apiFetch('/geofences').then(setGeofences).catch(() => {});
    apiFetch('/positions/latest').then(data => {
      const map = {};
      data.forEach(p => { map[p.device_id] = p; });
    }).catch(() => {});
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
