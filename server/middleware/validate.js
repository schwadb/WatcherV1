function validateCoordinates(lat, lng) {
  if (typeof lat !== 'number' || isNaN(lat) || lat < -90 || lat > 90) return false;
  if (typeof lng !== 'number' || isNaN(lng) || lng < -180 || lng > 180) return false;
  return true;
}

function validatePositionData(req, res, next) {
  const { latitude, longitude, speed, heading, accuracy } = req.body;

  const lat = parseFloat(latitude);
  const lng = parseFloat(longitude);
  if (!validateCoordinates(lat, lng)) {
    return res.status(400).json({ error: 'Invalid coordinates: latitude must be -90..90, longitude must be -180..180' });
  }
  req.body.latitude = lat;
  req.body.longitude = lng;

  if (speed !== undefined && speed !== null) {
    const s = parseFloat(speed);
    if (isNaN(s) || s < 0) return res.status(400).json({ error: 'Speed must be a non-negative number' });
    req.body.speed = s;
  }
  if (heading !== undefined && heading !== null) {
    const h = parseFloat(heading);
    if (isNaN(h) || h < 0 || h > 360) return res.status(400).json({ error: 'Heading must be 0..360' });
    req.body.heading = h;
  }
  if (accuracy !== undefined && accuracy !== null) {
    const a = parseFloat(accuracy);
    if (isNaN(a) || a < 0) return res.status(400).json({ error: 'Accuracy must be a non-negative number' });
    req.body.accuracy = a;
  }

  next();
}

function validateGeofenceData(req, res, next) {
  const { type, center_lat, center_lng, radius, coordinates } = req.body;

  if (type === 'circle') {
    const lat = parseFloat(center_lat);
    const lng = parseFloat(center_lng);
    const r = parseFloat(radius);
    if (!validateCoordinates(lat, lng)) {
      return res.status(400).json({ error: 'Invalid center coordinates' });
    }
    if (isNaN(r) || r <= 0 || r > 100000) {
      return res.status(400).json({ error: 'Radius must be between 0 and 100,000 meters' });
    }
    req.body.center_lat = lat;
    req.body.center_lng = lng;
    req.body.radius = r;
  }

  if (type === 'polygon') {
    if (!Array.isArray(coordinates) || coordinates.length < 3) {
      return res.status(400).json({ error: 'Polygon requires at least 3 coordinate pairs' });
    }
    for (const point of coordinates) {
      if (!Array.isArray(point) || point.length < 2 || !validateCoordinates(point[0], point[1])) {
        return res.status(400).json({ error: 'Each polygon coordinate must be a valid [lat, lng] pair' });
      }
    }
  }

  next();
}

module.exports = { validatePositionData, validateGeofenceData, validateCoordinates };
