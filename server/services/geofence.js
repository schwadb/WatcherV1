const db = require('../models/db');

function toRad(deg) {
  return deg * (Math.PI / 180);
}

function haversineDistance(lat1, lng1, lat2, lng2) {
  const R = 6371000;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function pointInPolygon(lat, lng, polygon) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [yi, xi] = polygon[i];
    const [yj, xj] = polygon[j];
    if ((yi > lng) !== (yj > lng) && lat < ((xj - xi) * (lng - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

function isInsideGeofence(lat, lng, geofence) {
  if (geofence.type === 'circle') {
    const dist = haversineDistance(lat, lng, geofence.center_lat, geofence.center_lng);
    return dist <= geofence.radius;
  }
  if (geofence.type === 'polygon') {
    const coords = typeof geofence.coordinates === 'string'
      ? JSON.parse(geofence.coordinates)
      : geofence.coordinates;
    return pointInPolygon(lat, lng, coords);
  }
  return false;
}

const deviceGeofenceState = new Map();

function checkGeofences(deviceId, lat, lng, io) {
  const geofences = db.prepare('SELECT * FROM geofences').all();

  for (const fence of geofences) {
    const inside = isInsideGeofence(lat, lng, fence);
    const stateKey = `${deviceId}:${fence.id}`;
    const wasInside = deviceGeofenceState.get(stateKey) || false;

    if (inside && !wasInside) {
      const eventType = 'enter';
      db.prepare(
        'INSERT INTO geofence_events (geofence_id, device_id, event_type) VALUES (?, ?, ?)'
      ).run(fence.id, deviceId, eventType);
      deviceGeofenceState.set(stateKey, true);
      if (io) io.emit('geofence:event', { geofence: fence.name, device_id: deviceId, event: eventType });
    } else if (!inside && wasInside) {
      const eventType = 'exit';
      db.prepare(
        'INSERT INTO geofence_events (geofence_id, device_id, event_type) VALUES (?, ?, ?)'
      ).run(fence.id, deviceId, eventType);
      deviceGeofenceState.set(stateKey, false);
      if (io) io.emit('geofence:event', { geofence: fence.name, device_id: deviceId, event: eventType });
    }
  }
}

module.exports = { checkGeofences, isInsideGeofence, haversineDistance };
