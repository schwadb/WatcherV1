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
const ph = (await api("/api/photos")).data.data;
check("photos carry caption, credit and memory fields", Array.isArray(ph.photos) && ph.photos.every((p) => "caption" in p && "credit" in p) && typeof ph.memories === "number", JSON.stringify(ph.photos.slice(0, 2)));
const wx = (await api("/api/weather")).data.data;
check("weather carries the nowcast, rain line and sun arc", wx.rain && wx.rain.kind === "starts" && wx.rain.soon === true && wx.sun && typeof wx.sun.progress === "number" && Array.isArray(wx.nowcast), JSON.stringify({ rain: wx.rain, sun: wx.sun }));
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
const newsNow = await api("/api/news");
check("ticker mixes quotes with headlines", newsNow.status === 200 && newsNow.data.data.headlines.some((h) => h.kind === "quote" && h.source === "Quote") && newsNow.data.data.headlines.every((h) => h.title.length <= 200), String(newsNow.status));
const photosNow = await api("/api/photos");
check("slideshow includes captioned paintings", photosNow.status === 200 && photosNow.data.data.photos.some((p) => p.art && p.caption), String((photosNow.data.data || {}).paintings));
const artOff = await api("/api/settings", { method: "PUT", json: { config: { photos: { seconds_per_photo: 20, order: "shuffle", max_upload_mb: 25, fit: "fit", art: false, art_every: 4, artists: "" }, todo: { max_items: 8 }, news: { feeds: [{ name: "NPR", url: "https://feeds.npr.org/1001/rss.xml" }], quotes: false, quote_every: 3 } } } });
const afterOff = await api("/api/settings");
check("paintings and quotes can be turned off", artOff.status === 200 && afterOff.data.config.photos.art === false && afterOff.data.config.news.quotes === false && (await api("/api/photos")).data.data.paintings === 0, JSON.stringify(afterOff.data.config.photos));
await api("/api/settings", { method: "PUT", json: { config: { photos: { seconds_per_photo: 20, order: "shuffle", max_upload_mb: 25, fit: "fit", art: true, art_every: 4, artists: "" }, todo: { max_items: 8 }, news: { feeds: [{ name: "NPR", url: "https://feeds.npr.org/1001/rss.xml" }], quotes: true, quote_every: 4 } } } });
const leagues = await api("/api/scores/leagues");
check("score leagues listed", leagues.status === 200 && leagues.data.leagues.length >= 3 && leagues.data.all.length >= leagues.data.leagues.length, JSON.stringify(leagues.data.leagues.map((l) => l.key)));
const board = await api("/api/scores?league=football/nfl");
check("scoreboard answers with games", board.status === 200 && board.data.games.length >= 3 && board.data.games[0].home.abbr, `${board.status} ${(board.data.games || []).length}`);
const allBoard = await api("/api/scores?league=all");
check("all-leagues board has sections and league tags", allBoard.status === 200 && allBoard.data.sections.length >= 2 && allBoard.data.games.every((g) => g.league && g.league_label), `${allBoard.status} ${(allBoard.data.sections || []).length}`);
const hsBoard = await api("/api/scores?league=nsaa/fb");
check("high school board answers from the NSAA page", hsBoard.status === 200 && hsBoard.data.games.length > 50 && hsBoard.data.note, `${hsBoard.status} ${(hsBoard.data.games || []).length}`);
const badLeague = await api("/api/scores?league=curling/olympics");
check("unknown league refused", badLeague.status === 404, String(badLeague.status));
const badLeagues = await api("/api/settings", { method: "PUT", json: { config: { scores: { leagues: ["nope/nope"] } } } });
check("empty league list rejected", badLeagues.status === 422, JSON.stringify(badLeagues.data));
await api("/api/settings", { method: "PUT", json: { config: { scores: { leagues: ["football/nfl", "football/college-football", "basketball/nba", "baseball/mlb", "hockey/nhl", "basketball/mens-college-basketball", "nsaa/fb", "nsaa/vb"], high_schools: ["Norris"] } } } });
const outputs = await api("/api/audio/outputs");
check("sound outputs listed", outputs.status === 200 && outputs.data.outputs.length >= 2 && outputs.data.outputs.every((o) => o.label && o.profile.startsWith("output:")), JSON.stringify(outputs.data));
const lib = await api("/api/music/library");
check("music library answers with playlists and device", lib.status === 200 && lib.data.playlists.length >= 2 && lib.data.device_name && typeof lib.data.paired === "boolean", JSON.stringify(lib.data).slice(0, 120));
const playRes = await api("/api/music/play", { method: "POST", json: { uri: lib.data.playlists[0].uri } });
check("play a playlist accepted", playRes.status === 200 && playRes.data.ok, JSON.stringify(playRes.data));
const badAction = await api("/api/music/explode", { method: "POST", json: {} });
check("unknown music action refused", badAction.status === 404, String(badAction.status));
const playerInfo = await api("/api/player");
check("player status answers", playerInfo.status === 200 && typeof playerInfo.data.installed === "boolean" && playerInfo.data.device_name, JSON.stringify(playerInfo.data));
const chronApp = await api("/api/chronalert/app");
check("ChronAlert app info answers", chronApp.status === 200 && "found_path" in chronApp.data && typeof chronApp.data.autostart === "boolean" && typeof chronApp.data.reachable === "boolean", JSON.stringify(chronApp.data));
const badAuto = await api("/api/chronalert/autostart", { method: "POST", json: { on: true, app_path: "/definitely/not/here.AppImage" } });
check("autostart with a missing AppImage is refused with a message", badAuto.status === 422 && /does not exist|not found/.test(badAuto.data.detail || ""), JSON.stringify(badAuto.data));
const chronStatus = await api("/api/chronalert/status");
check("ChronAlert reachability check answers", chronStatus.status === 200 && typeof chronStatus.data.reachable === "boolean" && chronStatus.data.url.startsWith("http"), JSON.stringify(chronStatus.data));
await api("/api/settings", { method: "PUT", json: { config: { weather: { takeover_minutes: 10, takeover_sound: true }, chronalert: { mode: "rotate", open_mode: "iframe", show_seconds: 20, photo_seconds: 20 } } } });
// ---- God's Eye View globe: settings, install (mock), and the globe.localhost proxy ---------------
const http = await import("node:http");
const rawGet = (path, headers) => new Promise((resolve, reject) => {
  const u = new URL(base);
  const req = http.request({ host: u.hostname, port: u.port || 80, path, method: "GET", headers, setHost: false }, (res) => {
    let body = ""; res.setEncoding("utf8"); res.on("data", (c) => body += c); res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, body }));
  });
  req.on("error", reject); req.end();
});
const basePort = new URL(base).port || "80";
const globeHeaders = { Host: `globe.localhost:${basePort}`, Origin: `http://globe.localhost:${basePort}`, Via: "1.1 test" };
const stub = http.createServer((req, res) => {
  res.setHeader("X-Frame-Options", "DENY"); res.setHeader("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'"); res.setHeader("Content-Type", "text/html");
  res.end(`<html><body id="stub">stub ${req.headers.host} ${req.headers.origin || "-"} ${req.headers.via || "-"} ${req.url}</body></html>`);
});
await new Promise((r) => stub.listen(0, "127.0.0.1", r));
const stubPort = stub.address().port;
const globeStatus = await api("/api/globe/status");
check("globe status answers", globeStatus.status === 200 && typeof globeStatus.data.reachable === "boolean" && globeStatus.data.port > 0, JSON.stringify(globeStatus.data));
const globeApp = await api("/api/globe/app");
check("globe app info answers", globeApp.status === 200 && typeof globeApp.data.installed === "boolean" && typeof globeApp.data.autostart === "boolean" && Array.isArray((globeApp.data.install || {}).log), JSON.stringify(globeApp.data));
const badPort = await api("/api/settings", { method: "PUT", json: { config: { globe: { enabled: false, port: 80 } } } });
check("globe port outside 1024-65535 rejected", badPort.status === 422, JSON.stringify(badPort.data));
const badGlobeAuto = await api("/api/globe/autostart", { method: "POST", json: { on: true } });
check("globe autostart refused before install", badGlobeAuto.status === 422 && /not installed/.test(badGlobeAuto.data.detail || ""), JSON.stringify(badGlobeAuto.data));
await api("/api/settings", { method: "PUT", json: { config: { globe: { enabled: false, port: stubPort } } } });
const inst = await api("/api/globe/install", { method: "POST", json: {} });
const instAgain = await api("/api/globe/install", { method: "POST", json: {} });
check("globe install starts once", inst.status === 200 && inst.data.install.running === true && instAgain.status === 409, `${inst.status} ${instAgain.status}`);
await new Promise((r) => setTimeout(r, 4500));
const instDone = await api("/api/globe/app");
check("mock install finishes and turns the TV button on", instDone.data.install.running === false && instDone.data.install.exit_code === 0 && instDone.data.enabled === true && (await api("/api/config")).data.globe.enabled === true, JSON.stringify(instDone.data.install));
const viaProxy = await rawGet("/hello?x=1", globeHeaders);
check("globe.localhost is proxied to the app with framing headers removed", viaProxy.status === 200 && !("x-frame-options" in viaProxy.headers) && viaProxy.headers["content-security-policy"] === "default-src 'self'" && viaProxy.body.includes(`stub 127.0.0.1:${stubPort} http://127.0.0.1:${stubPort} - /hello?x=1`), `${viaProxy.status} ${JSON.stringify(viaProxy.headers)} ${viaProxy.body}`);
const foreign = await rawGet("/", { ...globeHeaders, "X-Forwarded-For": "9.9.9.9" });  // uvicorn reads this as a client at 9.9.9.9
check("globe.localhost is refused for clients that are not this computer", foreign.status === 403, String(foreign.status));
const notGlobe = await rawGet("/api/config", { Host: `localhost:${basePort}` });
check("other host names are not proxied", notGlobe.status === 200 && notGlobe.body.includes("config_version"));
const badPkg = await api("/api/packages", { method: "POST", json: { number: "12", label: "x" } });
check("bad tracking number refused", badPkg.status === 422 && /tracking number/.test(badPkg.data.detail || ""), JSON.stringify(badPkg.data));
const pkg = await api("/api/packages", { method: "POST", json: { number: "1Z999AA10123456784", label: "New shoes" } });
check("package added (mock)", pkg.status === 200 && pkg.data.item.number === "1Z999AA10123456784", JSON.stringify(pkg.data));
const pkgDup = await api("/api/packages", { method: "POST", json: { number: "1z999aa10123456784", label: "again" } });
check("duplicate package refused", pkgDup.status === 409);
const pkgs = (await api("/api/packages")).data.data;
check("packages listed with a status and an arrival day", pkgs.items.some((p) => p.number === "1Z999AA10123456784" && p.status_text === "Out for delivery" && /Arriving/.test(p.eta_text)), JSON.stringify(pkgs.items));
const posted = await api("/api/messages", { method: "POST", json: { text: "Dad lands at 6:30", from: "Mom", ttl: "4h" } });
check("message posted", posted.status === 200 && posted.data.id && posted.data.expires, JSON.stringify(posted.data));
const badMsg = await api("/api/messages", { method: "POST", json: { text: "   ", ttl: "4h" } });
check("empty message refused", badMsg.status === 422);
const msgs = (await api("/api/messages")).data;
check("messages listed for the TV", msgs.data.items.some((m) => m.id === posted.data.id && m.text === "Dad lands at 6:30"), JSON.stringify(msgs.data));
const badNight = await api("/api/settings", { method: "PUT", json: { config: { display: { night_from: "25:99" } } } });
check("bad night-mode time rejected", badNight.status === 422 && /night_from/.test((badNight.data.errors || []).join(" ")), JSON.stringify(badNight.data));
const nowHM = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "America/Chicago" }).format(new Date());
const nightOn = await api("/api/settings", { method: "PUT", json: { config: { display: { night_mode: true, night_from: nowHM, night_to: nowHM < "23:00" ? "23:59" : "00:30" } } } });
check("night-mode window saved", nightOn.status === 200 && (await api("/api/config")).data.display.night_mode === true, JSON.stringify(nightOn.data));
const badClock = await api("/api/settings", { method: "PUT", json: { config: { clock: { style: "sideways" } } } });
check("unknown clock style rejected", badClock.status === 422 && /clock.style/.test((badClock.data.errors || []).join(" ")), JSON.stringify(badClock.data));
const ledClock = await api("/api/settings", { method: "PUT", json: { config: { clock: { style: "led" } } } });
check("clock style saved and visible", ledClock.status === 200 && (await api("/api/config")).data.clock.style === "led");
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
// the TV page: V opens the globe inside the dashboard (the stub stands in for the app)
const tv = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
const tvErrors = []; tv.on("pageerror", (e) => tvErrors.push(e.message));
await tv.goto(base + "/", { waitUntil: "load" });
await tv.waitForTimeout(2500); await tv.keyboard.press("Escape");
check("Globe button is on the TV menu", await tv.$eval("#globe-btn", (el) => !el.classList.contains("hidden")));
const clockInfo = await tv.evaluate(async () => { await document.fonts.ready; return { led: document.body.classList.contains("clock-led"), font: document.fonts.check("40px DSEG7"), time: document.getElementById("clock-time").textContent, ghost: document.getElementById("clock-ghost").textContent, date: document.getElementById("clock-date").textContent }; });
const nextInfo = await tv.evaluate(() => ({ hidden: document.getElementById("clock-next").classList.contains("hidden"), text: document.getElementById("clock-next").textContent, dot: document.getElementById("health-dot").className, title: document.getElementById("health-dot").title }));
check("what's next strip shows the live game and the next event", !nextInfo.hidden && /LIVE/.test(nextInfo.text) && /Lunch|in \d+ [mh]|Tomorrow/.test(nextInfo.text), JSON.stringify(nextInfo));
check("health dot reports the feeds", /health-dot (good|warn|bad)/.test(nextInfo.dot) && nextInfo.title.length > 0, JSON.stringify(nextInfo));
const pkgInfo = await tv.evaluate(() => ({ hidden: document.getElementById("packages").classList.contains("hidden"), text: document.getElementById("packages").textContent, hasTodo: document.body.classList.contains("has-todo") }));
check("TV lists the package under the to-do panel", !pkgInfo.hidden && /New shoes/.test(pkgInfo.text) && /Out for delivery/.test(pkgInfo.text) && pkgInfo.hasTodo, JSON.stringify(pkgInfo));
const msgInfo = await tv.evaluate(() => ({ hidden: document.getElementById("message-bar").classList.contains("hidden"), text: document.getElementById("message-text").textContent, meta: document.getElementById("message-meta").textContent }));
check("TV shows the family message", !msgInfo.hidden && msgInfo.text === "Dad lands at 6:30" && /Mom/.test(msgInfo.meta), JSON.stringify(msgInfo));
const nightInfo = await tv.evaluate(() => ({ night: document.body.classList.contains("night"), overlay: getComputedStyle(document.getElementById("dim-overlay")).opacity, ledColor: getComputedStyle(document.getElementById("clock-time")).color }));
check("night mode is on inside its window (dim overlay, red LED clock)", nightInfo.night && Number(nightInfo.overlay) > 0.3 && nightInfo.ledColor === "rgb(255, 74, 61)", JSON.stringify(nightInfo));
const wxInfo = await tv.evaluate(() => ({ rain: document.getElementById("weather-rain").textContent, soon: document.getElementById("weather-rain").classList.contains("soon"), dot: document.getElementById("sun-arc-dot").getAttribute("cx"), rise: document.getElementById("sun-arc-rise").textContent, anim: getComputedStyle(document.querySelector("#weather-icon .cloud, #weather-icon .rays, #weather-icon .moon, #weather-icon .fog") || document.body).animationName }));
check("weather panel shows the rain line and the sun arc; the icon animates only outside night mode", /starts around/.test(wxInfo.rain) && wxInfo.soon && wxInfo.dot !== "8" && wxInfo.rise.length > 0 && (nightInfo.night ? wxInfo.anim === "none" : wxInfo.anim !== "none"), JSON.stringify({ ...wxInfo, night: nightInfo.night }));
check("LED clock style is on with its font loaded", clockInfo.led && clockInfo.font && /^\d{1,2}:\d{2}$/.test(clockInfo.time) && /^8?8:88$/.test(clockInfo.ghost) && /^[A-Z]{3} [A-Z]{3} \d{1,2}$/.test(clockInfo.date), JSON.stringify(clockInfo));
await tv.keyboard.press("v"); await tv.waitForTimeout(2500);
const globeFrame = tv.frames().find((f) => f.url().startsWith("http://globe.localhost:"));
const globeShown = await tv.$eval("#globe-full", (el) => !el.classList.contains("hidden"));
const frameText = globeFrame ? await globeFrame.textContent("body").catch(() => "") : "";
check("V shows the globe frame from globe.localhost with the app inside", globeShown && globeFrame && frameText.includes("stub"), `${globeShown} ${globeFrame && globeFrame.url()} ${frameText}`);
await tv.keyboard.press("Escape"); await tv.waitForTimeout(400);
check("Escape closes the globe and blanks its frame", await tv.$eval("#globe-full", (el) => el.classList.contains("hidden")) && (await tv.$eval("#globe-full-frame", (el) => el.getAttribute("src"))) === "about:blank");
check("no TV page errors", tvErrors.length === 0, tvErrors.join(" | "));
await browser.close();
stub.close();
await new Promise((r) => setTimeout(r, 300));
const down = await rawGet("/", globeHeaders);
check("globe.localhost explains when the app is not running", down.status === 502 && down.body.includes("isn't running"), `${down.status}`);
await api("/api/settings", { method: "PUT", json: { config: { globe: { enabled: false, port: 4173 }, clock: { style: "led" }, display: { night_mode: true, night_from: "22:00", night_to: "06:00" } } } });
const pkgGone = await api("/api/packages/1Z999AA10123456784", { method: "DELETE" });
check("package removed", pkgGone.status === 200 && !(await api("/api/packages")).data.data.items.some((p) => p.number === "1Z999AA10123456784"));
const gone = await api(`/api/messages/${posted.data.id}`, { method: "DELETE" });
check("message removed", gone.status === 200 && !(await api("/api/messages")).data.data.items.some((m) => m.id === posted.data.id));
// cleanup to-do + note
for (const i of (await api("/api/todo")).data.data.items) await api(`/api/todo/${i.id}`, { method: "DELETE" });
await api("/api/notes", { method: "PUT", json: { text: "" } });
console.log(failures ? `\n${failures} check(s) FAILED` : "\nall manage checks passed");
process.exit(failures ? 1 : 0);
