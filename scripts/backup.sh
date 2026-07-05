#!/usr/bin/env bash
# Trigger a backup on the memory server, and optionally copy the newest
# backup file somewhere else (second disk, another share).
#
# Note: the server already runs its own scheduled backups (MCP_BACKUP_* in
# .env) into BACKUPS_DIR. Use this script for on-demand backups (e.g. right
# before an upgrade) or schedule it in UGOS Task Scheduler for an off-site copy.
#
# Usage: ./backup.sh <base-url> <api-key> [<backups-dir> <offsite-dir>]
#   e.g. ./backup.sh http://127.0.0.1:8000 mysecretkey
#        ./backup.sh http://127.0.0.1:8000 mysecretkey \
#            /volume1/docker/watcher-memory/backups /volume2/backup/watcher-memory
set -euo pipefail

BASE_URL=${1:?usage: backup.sh <base-url> <api-key> [<backups-dir> <offsite-dir>]}
API_KEY=${2:?usage: backup.sh <base-url> <api-key> [<backups-dir> <offsite-dir>]}
BACKUPS_DIR=${3:-}
OFFSITE_DIR=${4:-}
BASE_URL=${BASE_URL%/}

echo "Requesting backup..."
curl -fsS -H "X-API-Key: ${API_KEY}" -X POST "${BASE_URL}/api/backup/now" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("success"), d; print("  created {} ({} bytes in {:.1f}s)".format(d["filename"], d["size_bytes"], d["duration_seconds"]))'

echo "Backups on server:"
curl -fsS -H "X-API-Key: ${API_KEY}" "${BASE_URL}/api/backup/list" \
  | python3 -c 'import json,sys; [print("  {}  {} bytes  {}d old".format(b["filename"], b["size_bytes"], b["age_days"])) for b in json.load(sys.stdin).get("backups", [])]'

if [[ -n "${BACKUPS_DIR}" && -n "${OFFSITE_DIR}" ]]; then
  newest=$(ls -1t "${BACKUPS_DIR}" | head -n 1)
  if [[ -z "${newest}" ]]; then
    echo "No backup files found in ${BACKUPS_DIR}" >&2
    exit 1
  fi
  mkdir -p "${OFFSITE_DIR}"
  cp "${BACKUPS_DIR}/${newest}" "${OFFSITE_DIR}/"
  echo "Copied ${newest} -> ${OFFSITE_DIR}/"
fi

echo "Done."
