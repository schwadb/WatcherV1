const db = require('../models/db');
const logger = require('../logger');

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

function getBoundingBox(geofence) {
  if (geofence.type === 'circle') {
    const latDelta = geofence.radius / 111320;
    const lngDelta = geofence.radius / (111320 * Math.cos(toRad(geofence.center_lat)));
    return {
      minLat: geofence.center_lat - latDelta,
      maxLat: geofence.center_lat + latDelta,
      minLng: geofence.center_lng - lngDelta,
      maxLng: geofence.center_lng + lngDelta,
    };
  }
  if (geofence.type === 'polygon') {
    const coords = typeof geofence.coordinates === 'string'
      ? JSON.parse(geofence.coordinates)
      : geofence.coordinates;
    if (!coords || coords.length === 0) return null;
    let minLat = Infinity, maxLat = -Infinity, minLng = Infinity, maxLng = -Infinity;
    for (const [lat, lng] of coords) {
      if (lat < minLat) minLat = lat;
      if (lat > maxLat) maxLat = lat;
      if (lng < minLng) minLng = lng;
      if (lng > maxLng) maxLng = lng;
    }
    return { minLat, maxLat, minLng, maxLng };
  }
  return null;
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
let geofenceCache = null;
let geofenceBBoxCache = null;
let geofenceCacheTime = 0;
const CACHE_TTL = 30000;

function getCachedGeofences() {
  if (!geofenceCache || Date.now() - geofenceCacheTime > CACHE_TTL) {
    geofenceCache = db.prepare('SELECT * FROM geofences').all();
    geofenceBBoxCache = geofenceCache.map(f => ({
      fence: f,
      bbox: getBoundingBox(f),
    }));
    geofenceCacheTime = Date.now();
  }
  return geofenceBBoxCache;
}

function invalidateGeofenceCache() {
  geofenceCache = null;
  geofenceBBoxCache = null;
  geofenceCacheTime = 0;
}

function initGeofenceState() {
  const events = db.prepare(`
    SELECT device_id, geofence_id, event_type FROM geofence_events
    WHERE id IN (
      SELECT MAX(id) FROM geofence_events GROUP BY device_id, geofence_id
    )
  `).all();
  for (const evt of events) {
    deviceGeofenceState.set(`${evt.device_id}:${evt.geofence_id}`, evt.event_type === 'enter');
  }
}

initGeofenceState();

function checkGeofences(deviceId, lat, lng, io) {
  const geofencesWithBBox = getCachedGeofences();

  for (const { fence, bbox } of geofencesWithBBox) {
    if (bbox && (lat < bbox.minLat || lat > bbox.maxLat || lng < bbox.minLng || lng > bbox.maxLng)) {
      const stateKey = `${deviceId}:${fence.id}`;
      const wasInside = deviceGeofenceState.get(stateKey) || false;
      if (wasInside) {
        try {
          db.prepare(
            'INSERT INTO geofence_events (geofence_id, device_id, event_type) VALUES (?, ?, ?)'
          ).run(fence.id, deviceId, 'exit');
          deviceGeofenceState.set(stateKey, false);
          if (io) {
            const device = require('../models/device').findById(deviceId);
            if (device) {
              io.to(`user:${device.user_id}`).emit('geofence:event', {
                geofence: fence.name, device_id: deviceId, event: 'exit'
              });
            }
          }
        } catch (err) {
          logger.error({ err, deviceId, fenceId: fence.id }, 'Failed to record geofence exit event');
        }
      }
      continue;
    }

    const inside = isInsideGeofence(lat, lng, fence);
    const stateKey = `${deviceId}:${fence.id}`;
    const wasInside = deviceGeofenceState.get(stateKey) || false;

    if (inside !== wasInside) {
      const eventType = inside ? 'enter' : 'exit';
      try {
        db.prepare(
          'INSERT INTO geofence_events (geofence_id, device_id, event_type) VALUES (?, ?, ?)'
        ).run(fence.id, deviceId, eventType);
        deviceGeofenceState.set(stateKey, inside);
        if (io) {
          const device = require('../models/device').findById(deviceId);
          if (device) {
            io.to(`user:${device.user_id}`).emit('geofence:event', {
              geofence: fence.name, device_id: deviceId, event: eventType
            });
          }
        }
      } catch (err) {
        logger.error({ err, deviceId, fenceId: fence.id }, `Failed to record geofence ${eventType} event`);
      }
    }
  }
}

module.exports = { checkGeofences, isInsideGeofence, haversineDistance, invalidateGeofenceCache };
