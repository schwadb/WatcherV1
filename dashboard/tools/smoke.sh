#!/usr/bin/env bash
# Check every API endpoint on a running server.  Usage: bash tools/smoke.sh [http://127.0.0.1:8080]
BASE="${1:-http://127.0.0.1:8080}"
fail=0
for name in config health weather alerts radar stocks sports calendar news photos todo notes nowplaying display; do
  code="$(curl -s -o /tmp/smoke_body -w "%{http_code}" "$BASE/api/$name")"
  if [ "$code" = "404" ] && [[ "$name" =~ ^(alerts|sports|nowplaying)$ ]]; then echo "skip  /api/$name   (not configured)"; continue; fi
  if [ "$code" != "200" ]; then echo "FAIL  /api/$name  (HTTP $code)"; fail=1; continue; fi
  python3 - "$name" "$(cat /tmp/smoke_body)" <<'EOF' || fail=1
import json, sys
name, body = sys.argv[1], sys.argv[2]
d = json.loads(body)
if name == "config":
    assert "timezone" in d and "symbols" in d and "panels" in d, "config missing keys"
    print(f"ok    /api/config     tz={d['timezone']} symbols={list(d['symbols'])} countdowns={len(d['countdowns'])} version={d['config_version']}")
elif name == "display":
    print(f"ok    /api/display    mode={d['mode']} schedule_enabled={d['schedule_enabled']} desired_now={d['desired_now']} last={d['last_result']}")
elif name == "health":
    bad = {k: v["error"] for k, v in d["sources"].items() if not v["ok"]}
    print(f"ok    /api/health     all_ok={d['ok']} failing={bad or 'none'}")
else:
    assert d["source"] == name, "wrong source"
    status = "ok   " if d["ok"] else "warn "
    detail = ""
    data = d.get("data") or {}
    if name == "weather" and d["ok"]:
        detail = f"{data['current']['temp']}{data['units']['temp']} {data['current']['label']}, {len(data['daily'])} days, {len(data['hourly'])} hours, uv={data['today']['uv']}, air={(data.get('air') or {}).get('label')}, moon={data['moon']['name']}"
    if name == "alerts" and d["ok"]: detail = f"{data['count']} active" + (f": {data['top']['event']}" if data['top'] else "")
    if name == "radar" and d["ok"]: detail = f"{data['provider']} {len(data['frames'])} frames"
    if name == "stocks" and d["ok"]: detail = ", ".join(f"{q['symbol']} {q['price']}" for q in data["quotes"])
    if name == "sports" and d["ok"]:
        t = data["teams"][0]; detail = f"{t['short']} {t['record']} | next {t['next']['short_name'] if t['next'] else '-'} | last {t['last']['result'] if t['last'] else '-'}"
    if name == "calendar" and d["ok"]: detail = f"{data['count']} events over {len(data['days'])} days from {[c['name'] for c in data.get('calendars', [])]}"
    if name == "news" and d["ok"]: detail = f"{len(data['headlines'])} headlines"
    if name == "photos" and d["ok"]: detail = f"{len(data['photos'])} photos"
    if name == "todo": detail = f"{len(data['items'])} items"
    if name == "notes": detail = f"{len(data.get('text') or '')} chars"
    if name == "nowplaying" and d["ok"]: detail = f"playing={data['playing']} {data.get('title', '')}"
    if not d["ok"]: detail = f"error: {d['error']}"
    print(f"{status} /api/{name:<10} {detail}")
EOF
done
[ $fail -eq 0 ] && echo "smoke test passed" || { echo "smoke test FAILED"; exit 1; }
