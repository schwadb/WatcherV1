import { useState } from 'react';
import { apiFetch } from '../utils/api';

export default function DeviceList({ devices, setDevices, positions, onSelect }) {
  const [form, setForm] = useState({ name: '', unique_id: '', type: 'vehicle' });
  const [adding, setAdding] = useState(false);

  async function addDevice(e) {
    e.preventDefault();
    try {
      const device = await apiFetch('/devices', { method: 'POST', body: JSON.stringify(form) });
      setDevices(prev => [...prev, device]);
      setForm({ name: '', unique_id: '', type: 'vehicle' });
      setAdding(false);
    } catch (err) {
      alert(err.message);
    }
  }

  async function removeDevice(id) {
    if (!confirm('Delete this device?')) return;
    try {
      await apiFetch(`/devices/${id}`, { method: 'DELETE' });
      setDevices(prev => prev.filter(d => d.id !== id));
    } catch (err) {
      alert(err.message);
    }
  }

  return (
    <div className="device-list">
      <div className="device-list-header">
        <h3>Devices ({devices.length})</h3>
        <button onClick={() => setAdding(!adding)}>+</button>
      </div>

      {adding && (
        <form onSubmit={addDevice} className="device-form">
          <input placeholder="Name" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required />
          <input placeholder="Unique ID" value={form.unique_id} onChange={e => setForm(f => ({ ...f, unique_id: e.target.value }))} required />
          <select value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))}>
            <option value="vehicle">Vehicle</option>
            <option value="person">Person</option>
            <option value="asset">Asset</option>
          </select>
          <button type="submit">Add</button>
        </form>
      )}

      <ul>
        {devices.map(d => {
          const pos = positions[d.id];
          return (
            <li key={d.id} className={`device-item ${d.status}`} onClick={() => onSelect(d.id)}>
              <div className="device-info">
                <span className={`status-dot ${d.status}`} />
                <strong>{d.name}</strong>
                <span className="device-type">{d.type}</span>
              </div>
              {pos && <small>{pos.speed ? `${pos.speed.toFixed(1)} km/h` : 'Stationary'}</small>}
              <button className="delete-btn" onClick={e => { e.stopPropagation(); removeDevice(d.id); }}>x</button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
