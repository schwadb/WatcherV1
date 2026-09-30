#!/usr/bin/env bash
# Check every API endpoint on a running server.  Usage: bash tools/smoke.sh [http://127.0.0.1:8080]
BASE="${1:-http://127.0.0.1:8080}"
fail=0
for name in config health weather radar stocks calendar news photos; do
  body="$(curl -sf "$BASE/api/$name")" || { echo "FAIL  /api/$name  (no response)"; fail=1; continue; }
  python3 - "$name" "$body" <<'EOF' || fail=1
import json, sys
name, body = sys.argv[1], sys.argv[2]
d = json.loads(body)
if name == "config":
    assert "timezone" in d and "symbols" in d, "config missing keys"
    print(f"ok    /api/config     tz={d['timezone']} symbols={list(d['symbols'])}")
elif name == "health":
    bad = {k: v["error"] for k, v in d["sources"].items() if not v["ok"]}
    print(f"ok    /api/health     all_ok={d['ok']} failing={bad or 'none'}")
else:
    assert d["source"] == name, "wrong source"
    status = "ok   " if d["ok"] else "warn "
    detail = ""
    data = d.get("data") or {}
    if name == "weather" and d["ok"]: detail = f"{data['current']['temp']}{data['units']['temp']} {data['current']['label']}, {len(data['daily'])} days"
    if name == "radar" and d["ok"]: detail = f"{data['provider']} {len(data['frames'])} frames"
    if name == "stocks" and d["ok"]: detail = ", ".join(f"{q['symbol']} {q['price']}" for q in data["quotes"])
    if name == "calendar" and d["ok"]: detail = f"{data['count']} events over {len(data['days'])} days"
    if name == "news" and d["ok"]: detail = f"{len(data['headlines'])} headlines"
    if name == "photos" and d["ok"]: detail = f"{len(data['photos'])} photos"
    if not d["ok"]: detail = f"error: {d['error']}"
    print(f"{status} /api/{name:<10} {detail}")
EOF
done
[ $fail -eq 0 ] && echo "smoke test passed" || { echo "smoke test FAILED"; exit 1; }
