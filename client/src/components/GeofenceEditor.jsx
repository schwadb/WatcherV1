import { useState } from 'react';
import { apiFetch } from '../utils/api';

export default function GeofenceEditor({ geofences, setGeofences }) {
  const [form, setForm] = useState({ name: '', center_lat: '', center_lng: '', radius: '500' });
  const [adding, setAdding] = useState(false);

  async function addGeofence(e) {
    e.preventDefault();
    try {
      const data = {
        name: form.name,
        type: 'circle',
        center_lat: parseFloat(form.center_lat),
        center_lng: parseFloat(form.center_lng),
        radius: parseFloat(form.radius)
      };
      const fence = await apiFetch('/geofences', { method: 'POST', body: JSON.stringify(data) });
      setGeofences(prev => [...prev, { ...data, id: fence.id }]);
      setForm({ name: '', center_lat: '', center_lng: '', radius: '500' });
      setAdding(false);
    } catch (err) {
      alert(err.message);
    }
  }

  async function removeGeofence(id) {
    try {
      await apiFetch(`/geofences/${id}`, { method: 'DELETE' });
      setGeofences(prev => prev.filter(g => g.id !== id));
    } catch (err) {
      alert(err.message);
    }
  }

  return (
    <div className="geofence-editor">
      <div className="device-list-header">
        <h3>Geofences ({geofences.length})</h3>
        <button onClick={() => setAdding(!adding)}>+</button>
      </div>

      {adding && (
        <form onSubmit={addGeofence} className="device-form">
          <input placeholder="Name" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required />
          <input placeholder="Center Lat" type="number" step="any" value={form.center_lat} onChange={e => setForm(f => ({ ...f, center_lat: e.target.value }))} required />
          <input placeholder="Center Lng" type="number" step="any" value={form.center_lng} onChange={e => setForm(f => ({ ...f, center_lng: e.target.value }))} required />
          <input placeholder="Radius (m)" type="number" value={form.radius} onChange={e => setForm(f => ({ ...f, radius: e.target.value }))} required />
          <button type="submit">Add</button>
        </form>
      )}

      <ul>
        {geofences.map(g => (
          <li key={g.id} className="device-item">
            <div className="device-info">
              <strong>{g.name}</strong>
              <span className="device-type">{g.type} {g.radius ? `${g.radius}m` : ''}</span>
            </div>
            <button className="delete-btn" onClick={() => removeGeofence(g.id)}>x</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
