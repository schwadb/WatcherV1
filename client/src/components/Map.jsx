import { MapContainer, TileLayer, Marker, Popup, Circle, Polyline, useMap } from 'react-leaflet';
import { useEffect, useRef } from 'react';
import L from 'leaflet';

const icon = new L.Icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
});

function FitBounds({ positions, selectedDevice }) {
  const map = useMap();
  const hasFitted = useRef(false);
  const prevSelected = useRef(null);

  useEffect(() => {
    if (selectedDevice && selectedDevice !== prevSelected.current) {
      prevSelected.current = selectedDevice;
      const pos = positions[selectedDevice];
      if (pos) {
        map.setView([pos.latitude, pos.longitude], 15, { animate: true });
      }
      return;
    }

    if (!hasFitted.current) {
      const points = Object.values(positions);
      if (points.length > 0) {
        const bounds = points.map(p => [p.latitude, p.longitude]);
        map.fitBounds(bounds, { padding: [50, 50], maxZoom: 15 });
        hasFitted.current = true;
      }
    }
  }, [positions, selectedDevice, map]);

  return null;
}

export default function TrackingMap({ positions, geofences = [], track = null, selectedDevice }) {
  const center = [39.8283, -98.5795];

  return (
    <MapContainer center={center} zoom={4} style={{ height: '100%', width: '100%' }}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds positions={positions} selectedDevice={selectedDevice} />

      {Object.entries(positions).map(([deviceId, pos]) => (
        <Marker key={deviceId} position={[pos.latitude, pos.longitude]} icon={icon}>
          <Popup>
            <strong>{pos.device_name || `Device ${deviceId}`}</strong><br />
            Speed: {pos.speed != null ? `${pos.speed.toFixed(1)} km/h` : 'N/A'}<br />
            Updated: {new Date(pos.timestamp).toLocaleTimeString()}
          </Popup>
        </Marker>
      ))}

      {geofences.map(g => g.type === 'circle' && (
        <Circle
          key={g.id}
          center={[g.center_lat, g.center_lng]}
          radius={g.radius}
          pathOptions={{ color: '#6366f1', fillOpacity: 0.1 }}
        />
      ))}

      {track && track.length > 1 && (
        <Polyline
          positions={track.map(p => [p.latitude, p.longitude])}
          pathOptions={{ color: '#3b82f6', weight: 3 }}
        />
      )}
    </MapContainer>
  );
}
