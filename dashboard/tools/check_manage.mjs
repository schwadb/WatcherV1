// End-to-end checks for the settings page against a running server (mock mode recommended).
// Usage: DASHBOARD_PIN=1234 node tools/check_manage.mjs http://127.0.0.1:8081 /path/to/sample.jpg /path/to/sample.heic /path/to/junk.jpg
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright");

const [base = "http://127.0.0.1:8081", jpg, heic, junk] = process.argv.slice(2);
const PIN = process.env.DASHBOARD_PIN || "";
let failures = 0;
const check = (label, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + label + (extra ? `  (${extra})` : "")); if (!ok) failures++; };
const api = async (path, opts = {}) => {
  const headers = { ...(opts.headers || {}) };
  if (PIN) headers["X-Pin"] = PIN;
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
  const r = await fetch(base + path, { ...opts, headers });
  let data = null; try { data = await r.json(); } catch (e) {}
  return { status: r.status, data };
};

// ---- API level -------------------------------------------------------------------------------
if (PIN) {
  const r = await fetch(base + "/api/todo", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: "no pin" }) });
  check("write without PIN is refused (401)", r.status === 401, String(r.status));
  const g = await fetch(base + "/api/settings");
  check("settings read without PIN is refused (401)", g.status === 401, String(g.status));
}
const before = (await api("/api/config")).data.config_version;
const item = await api("/api/todo", { method: "POST", json: { text: "Buy milk" } });
check("add to-do item", item.status === 200 && item.data.text === "Buy milk");
const patched = await api(`/api/todo/${item.data.id}`, { method: "PATCH", json: { done: true } });
check("check off to-do item", patched.status === 200 && patched.data.done === true && patched.data.done_on);
const list = await api("/api/todo");
check("to-do list shows the item", list.data.data.items.some((i) => i.id === item.data.id));
const note = await api("/api/notes", { method: "PUT", json: { text: "Dinner at 6" } });
check("save note", note.status === 200 && note.data.text === "Dinner at 6");
const settings = await api("/api/settings");
check("settings read with PIN", settings.status === 200 && settings.data.config.location && settings.data.secrets.FINNHUB_API_KEY, JSON.stringify(settings.data.secrets && settings.data.secrets.FINNHUB_API_KEY));
const bad = await api("/api/settings", { method: "PUT", json: { config: { location: { name: "X", lat: 999, lon: 0, timezone: "Mars/Olympus" } } } });
check("invalid settings rejected with messages", bad.status === 422 && bad.data.errors.length >= 2, (bad.data.errors || []).join(" | "));
const good = await api("/api/settings", { method: "PUT", json: { config: { location: { name: "Lincoln, NE", lat: 40.8, lon: -96.7, timezone: "America/Chicago" }, countdowns: [{ title: "Test day", date: "2099-01-01", icon: "🎉" }], panels: { radar: false } } } });
check("valid settings saved", good.status === 200 && good.data.ok, JSON.stringify(good.data));
const after = (await api("/api/config")).data;
check("hot reload bumped config_version", after.config_version === before + 1, `${before} -> ${after.config_version}`);
check("new location visible without restart", after.location.name === "Lincoln, NE" && after.countdowns.some((c) => c.title === "Test day") && after.panels.radar === false);
const health = (await api("/api/health")).data;
check("sources still ok after reload (radar removed)", !("radar" in health.sources) && health.sources.weather.ok);
const zip = await api("/api/zip/68424");
check("ZIP lookup", zip.status === 200 && zip.data.name.startsWith("Plymouth") && zip.data.timezone === "America/Chicago", JSON.stringify(zip.data));
const badChron = await api("/api/settings", { method: "PUT", json: { config: { weather: { takeover_minutes: 500 }, chronalert: { mode: "sideways", url: "ftp://nope", show_seconds: 1 } } } });
check("bad storm-mode / ChronAlert settings rejected", badChron.status === 422 && badChron.data.errors.length >= 3, (badChron.data.errors || []).join(" | "));
const goodChron = await api("/api/settings", { method: "PUT", json: { config: { weather: { takeover: true, takeover_minutes: 15, takeover_sound: false }, chronalert: { mode: "button", url: "http://127.0.0.1:8420/", show_seconds: 60, photo_seconds: 120, open_mode: "window" } } } });
const chronCfg = goodChron.status === 200 ? (await api("/api/config")).data : {};
check("storm-mode / ChronAlert settings saved and visible", goodChron.status === 200 && chronCfg.takeover && chronCfg.takeover.takeover_minutes === 15 && chronCfg.takeover.takeover_sound === false && chronCfg.chronalert && chronCfg.chronalert.mode === "button" && chronCfg.chronalert.open_mode === "window", JSON.stringify([goodChron.data, chronCfg.takeover, chronCfg.chronalert]));
const stockSearch = await api("/api/stocks/search?q=apple");
check("stock search (mock) finds AAPL", stockSearch.status === 200 && stockSearch.data.results.some((r) => r.symbol === "AAPL" && r.name === "Apple"), JSON.stringify(stockSearch.data));
const catalog = await api("/api/news/catalog");
check("feed catalogue has groups", catalog.status === 200 && catalog.data.groups.length >= 4 && catalog.data.groups.every((g) => g.feeds.length), String(catalog.status));
// A tiny web server over fixtures/ stands in for a news site (site.html advertises news.xml).
const { spawn } = await import("node:child_process");
const fixtures = new URL("../fixtures/", import.meta.url).pathname;
const site = spawn("python3", ["-m", "http.server", "8766", "--bind", "127.0.0.1"], { cwd: fixtures, stdio: "ignore" });
await new Promise((r) => setTimeout(r, 1200));
try {
  const found = await api("/api/news/find?url=" + encodeURIComponent("http://127.0.0.1:8766/site.html"));
  check("feed finder follows the page's feed link", found.status === 200 && found.data.url === "http://127.0.0.1:8766/news.xml" && found.data.name === "Sample News" && found.data.sample, JSON.stringify(found.data));
  const none = await api("/api/news/find?url=" + encodeURIComponent("http://127.0.0.1:8766/nothing-here"));
  check("feed finder explains when nothing is found", none.status === 404 && /No news feed/.test(none.data.detail || ""), JSON.stringify(none.data));
} finally { site.kill(); }
const chronApp = await api("/api/chronalert/app");
check("ChronAlert app info answers", chronApp.status === 200 && "found_path" in chronApp.data && typeof chronApp.data.autostart === "boolean" && typeof chronApp.data.reachable === "boolean", JSON.stringify(chronApp.data));
const badAuto = await api("/api/chronalert/autostart", { method: "POST", json: { on: true, app_path: "/definitely/not/here.AppImage" } });
check("autostart with a missing AppImage is refused with a message", badAuto.status === 422 && /does not exist|not found/.test(badAuto.data.detail || ""), JSON.stringify(badAuto.data));
const chronStatus = await api("/api/chronalert/status");
check("ChronAlert reachability check answers", chronStatus.status === 200 && typeof chronStatus.data.reachable === "boolean" && chronStatus.data.url.startsWith("http"), JSON.stringify(chronStatus.data));
await api("/api/settings", { method: "PUT", json: { config: { weather: { takeover_minutes: 10, takeover_sound: true }, chronalert: { mode: "rotate", open_mode: "iframe", show_seconds: 20, photo_seconds: 20 } } } });
const sysinfo = await api("/api/system");
check("system info", sysinfo.status === 200 && typeof sysinfo.data.disk_free_gb === "number" && sysinfo.data.version);
// restore
await api("/api/settings", { method: "PUT", json: { config: { location: { name: "Plymouth, NE", lat: 40.3039, lon: -97.0012, timezone: "America/Chicago" }, panels: { radar: true } } } });

// ---- uploads ---------------------------------------------------------------------------------
if (jpg) {
  const fs = await import("node:fs");
  const form = new FormData();
  form.append("files", new Blob([fs.readFileSync(jpg)], { type: "image/jpeg" }), "my photo (1).jpg");
  if (heic) form.append("files", new Blob([fs.readFileSync(heic)]), "IMG_0001.HEIC");
  if (junk) form.append("files", new Blob([fs.readFileSync(junk)]), "junk.jpg");
  form.append("files", new Blob([new Uint8Array([1, 2, 3])]), "notes.txt");
  const up = await fetch(base + "/api/photos/upload", { method: "POST", body: form, headers: PIN ? { "X-Pin": PIN } : {} });
  const d = await up.json();
  check("upload JPEG saved with a safe name", up.status === 200 && d.saved.some((n) => /-my_photo_1_.jpg$|my_photo/.test(n)), JSON.stringify(d.saved));
  if (heic) check("HEIC converted to JPEG", d.saved.some((n) => n.endsWith(".jpg") && !/my_photo/.test(n)), JSON.stringify(d.saved));
  check("junk and .txt rejected with reasons", d.rejected.length === (junk ? 2 : 1) && d.rejected.every((r) => r.reason), JSON.stringify(d.rejected));
  const listing = (await api("/api/photos/list")).data;
  check("photo list includes uploads with thumbnails", d.saved.every((n) => listing.photos.some((p) => p.name === n && p.thumb)));
  const slideshow = (await api("/api/photos")).data.data;
  check("slideshow picked up the uploads", d.saved.every((n) => slideshow.photos.some((p) => p.name === n)));
  const traversal = await api("/api/photos/..%2Fconfig.yaml", { method: "DELETE" });
  check("path traversal delete refused", traversal.status === 404, String(traversal.status));
  for (const n of d.saved) await api(`/api/photos/${encodeURIComponent(n)}`, { method: "DELETE" });
  const gone = (await api("/api/photos/list")).data;
  check("delete removes uploads", d.saved.every((n) => !gone.photos.some((p) => p.name === n)));
}

// ---- browser level ---------------------------------------------------------------------------
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto(base + "/manage#settings", { waitUntil: "load" });
if (PIN) {
  await page.fill("#pin-input", PIN);
  await page.click("#pin-form button");
}
await page.waitForTimeout(1500);
const nameValue = await page.inputValue('input[name="location.name"]');
check("settings form filled from server", nameValue === "Plymouth, NE", nameValue);
const stocksBefore = await page.$$eval("#stock-list .item", (els) => els.length);
await page.click('#stock-picks button[title="Nvidia"]');
await page.waitForTimeout(300);
await page.click('#stock-picks button[title="Nvidia"]');  // second tap must not duplicate
await page.waitForTimeout(300);
const stocksAfter = await page.$$eval("#stock-list .item", (els) => els.length);
const lastSym = await page.$eval("#stock-list .item:last-child .sym", (el) => el.value);
check("quick pick adds a stock row once", stocksAfter === stocksBefore + 1 && lastSym === "NVDA", `${stocksBefore} -> ${stocksAfter} ${lastSym}`);
await page.click("#feed-groups button");  // first catalogue group
await page.waitForTimeout(200);
const feedsBefore = await page.$$eval("#feed-list .item", (els) => els.length);
await page.click("#feed-catalog button:not(.have)");  // one that is not on the list yet
await page.waitForTimeout(300);
const feedsAfter = await page.$$eval("#feed-list .item", (els) => els.length);
const lastFeedUrl = await page.$eval("#feed-list .item:last-child .url", (el) => el.value);
check("catalogue tap adds a feed row", feedsAfter === feedsBefore + 1 && lastFeedUrl.startsWith("http"), `${feedsBefore} -> ${feedsAfter} ${lastFeedUrl}`);
await page.click('a[data-tab="todo"]');
await page.waitForTimeout(800);
await page.fill("#todo-input", "Walk the dog");
await page.click("#todo-form button");
await page.waitForTimeout(800);
const todoText = await page.textContent("#todo-items");
check("to-do added from the page", todoText.includes("Walk the dog"));
await page.screenshot({ path: process.env.SHOT_MANAGE || "manage.png", fullPage: false });
await page.goto(base + "/manage?kiosk=1#todo", { waitUntil: "load" });
await page.waitForTimeout(800);
await page.focus("#todo-input");
await page.waitForTimeout(300);
const kbdVisible = await page.isVisible("#kbd");
check("kiosk mode shows the on-screen keyboard", kbdVisible);
await page.click('#kbd button[data-k="h"]'); await page.click('#kbd button[data-k="i"]');
check("on-screen keyboard types", (await page.inputValue("#todo-input")) === "hi");
check("no page errors", errors.length === 0, errors.join(" | "));
await browser.close();
// cleanup to-do + note
for (const i of (await api("/api/todo")).data.data.items) await api(`/api/todo/${i.id}`, { method: "DELETE" });
await api("/api/notes", { method: "PUT", json: { text: "" } });
console.log(failures ? `\n${failures} check(s) FAILED` : "\nall manage checks passed");
process.exit(failures ? 1 : 0);
