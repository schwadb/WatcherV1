const db = require('../models/db');
const logger = require('../logger');

const STALE_THRESHOLD_MS = parseInt(process.env.STALE_DEVICE_MS) || 5 * 60 * 1000;
const CHECK_INTERVAL_MS = 60 * 1000;
let intervalId = null;

function markStaleDevices() {
  const cutoff = new Date(Date.now() - STALE_THRESHOLD_MS).toISOString();
  const result = db.prepare(
    `UPDATE devices SET status = 'inactive'
     WHERE status = 'active' AND last_seen < ?`
  ).run(cutoff);
  if (result.changes > 0) {
    logger.info({ count: result.changes }, 'Marked stale devices inactive');
  }
}

function startStaleDeviceChecker() {
  markStaleDevices();
  intervalId = setInterval(markStaleDevices, CHECK_INTERVAL_MS);
}

function stopStaleDeviceChecker() {
  if (intervalId) {
    clearInterval(intervalId);
    intervalId = null;
  }
}

module.exports = { startStaleDeviceChecker, stopStaleDeviceChecker };
