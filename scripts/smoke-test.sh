#!/usr/bin/env bash
# End-to-end check of the memory server: health -> store -> semantic search -> delete.
# Run from any device that can reach the server (needs curl + python3).
#
# Usage: ./smoke-test.sh <base-url> <api-key>
#   e.g. ./smoke-test.sh http://100.64.0.5:8000 mysecretkey
set -euo pipefail

BASE_URL=${1:?usage: smoke-test.sh <base-url> <api-key>}
API_KEY=${2:?usage: smoke-test.sh <base-url> <api-key>}
BASE_URL=${BASE_URL%/}
auth=(-H "X-API-Key: ${API_KEY}")
json=(-H "Content-Type: application/json")

echo "1/4 health check..."
curl -fsS --max-time 10 "${BASE_URL}/api/health" >/dev/null
echo "    ok"

marker="smoke-test-$$-$(date +%s)"
echo "2/4 storing a test memory..."
hash=$(curl -fsS "${auth[@]}" "${json[@]}" -X POST "${BASE_URL}/api/memories" \
  -d "{\"content\": \"Smoke test memory ${marker}: the Watcher memory deployment kit is working.\", \"tags\": [\"smoke-test\"], \"memory_type\": \"note\"}" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("success"), d; print(d["content_hash"])')
echo "    stored ${hash}"

echo "3/4 semantic search for it..."
curl -fsS "${auth[@]}" "${json[@]}" -X POST "${BASE_URL}/api/search" \
  -d '{"query": "smoke test of the watcher memory deployment kit", "n_results": 5}' \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
hashes = [r['memory']['content_hash'] for r in d.get('results', [])]
assert '${hash}' in hashes, f'stored memory not found in search results: {hashes}'
print(f\"    found it ({d.get('total_found')} result(s))\")"

echo "4/4 deleting the test memory..."
curl -fsS "${auth[@]}" -X DELETE "${BASE_URL}/api/memories/${hash}" >/dev/null
echo "    ok"

echo "PASS: store -> semantic search -> delete round trip succeeded."
