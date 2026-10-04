/* Watcher Dashboard front end. Polls /api/* and renders each panel. No build step, no frameworks. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = { config: null, failures: 0, startedAt: Date.now(), configVersion: null };

  // ---------- helpers ----------------------------------------------------------------------
  async function getJSON(path) {
    const resp = await fetch(path, { cache: "no-store" });
    if (!resp.ok) throw new Error(`${path} -> HTTP ${resp.status}`);
    return resp.json();
  }

  function tz() { return (state.config && state.config.timezone) || undefined; }
  function hour12() { return !(state.config && state.config.clock_24h); }
  function cfg(path, fallback) {
    let cur = state.config;
    for (const key of path.split(".")) { if (cur == null) return fallback; cur = cur[key]; }
    return cur == null ? fallback : cur;
  }

  function fmtTime(date) {
    return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", hour12: hour12(), timeZone: tz() }).format(date);
  }
  function fmtParts(date, opts) {
    const parts = new Intl.DateTimeFormat("en-US", { ...opts, hour12: hour12(), timeZone: tz() }).formatToParts(date);
    return (t) => (parts.find((p) => p.type === t) || {}).value || "";
  }
  function fmtShortTime(date) {
    // "9 AM", "12:30 PM" — compact for agenda rows
    const get = fmtParts(date, { hour: "numeric", minute: "2-digit" });
    const minute = get("minute");
    const ampm = get("dayPeriod");
    return `${get("hour")}${minute === "00" && hour12() ? "" : ":" + minute}${ampm ? " " + ampm : ""}`;
  }
  /** Open-Meteo sends local wall-clock times like "2026-09-30T07:23" (no zone). Format them as-is. */
  function fmtLocalClock(localIso, hourOnly) {
    const m = /T(\d{2}):(\d{2})/.exec(localIso || "");
    if (!m) return "";
    let h = Number(m[1]);
    const min = m[2];
    if (!hour12()) return hourOnly ? `${m[1]}:00` : `${m[1]}:${min}`;
    const ampm = h >= 12 ? "PM" : "AM";
    h = h % 12 || 12;
    return hourOnly ? `${h} ${ampm}` : `${h}:${min} ${ampm}`;
  }
  function weekdayShort(isoDate) {
    const d = new Date(isoDate + "T12:00:00");
    return new Intl.DateTimeFormat("en-US", { weekday: "short" }).format(d);
  }
  function todayISO() {
    const get = fmtParts(new Date(), { year: "numeric", month: "2-digit", day: "2-digit" });
    return `${get("year")}-${get("month")}-${get("day")}`;
  }
  function ago(seconds) {
    if (seconds == null) return "never";
    if (seconds < 90) return "just now";
    if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
    if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
    return `${Math.round(seconds / 86400)} d ago`;
  }
  function setBadge(name, env, clientError) {
    const badge = $(`badge-${name}`);
    if (!badge) return;
    badge.classList.remove("show", "error");
    if (clientError) {
      badge.textContent = "connection lost";
      badge.classList.add("show");
    } else if (!env.ok) {
      badge.textContent = "no data: " + (env.error || "waiting for first update").replace(/^\w+Error: /, "");
      badge.classList.add("show", "error");
    } else if (env.stale) {
      badge.textContent = "updated " + ago(env.age_seconds);
      badge.classList.add("show");
    }
  }
  function escapeHTML(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  /** Friendly in-panel hints for the sources that need something from the user. */
  const HINTS = {
    calendar: { needles: ["OUTLOOK_ICS_URL", "link not set"], text: "Add your calendar link on the settings page (or OUTLOOK_ICS_URL in the .env file on the Pi)." },
    stocks: { needles: ["FINNHUB_API_KEY"], text: "Add a free Finnhub key on the settings page (or FINNHUB_API_KEY in the .env file on the Pi)." },
  };
  function renderEmpty(name, env) {
    const hint = HINTS[name];
    const target = name === "calendar" ? $("agenda") : name === "stocks" ? $("quotes") : null;
    if (!target || target.dataset.hasData) return;
    const err = env.error || "";
    const msg = hint && hint.needles.some((n) => err.includes(n)) ? hint.text : err ? "Waiting for data…" : "Loading…";
    target.innerHTML = `<div class="muted hint">${escapeHTML(msg)}</div>`;
  }

  /** Poll one endpoint forever. The renderer only runs when the server has data. */
  function startWidget(name, intervalSeconds, render, onMissing) {
    let timer = null;
    async function tick() {
      try {
        const env = await getJSON(`/api/${name}`);
        state.failures = 0;
        setBadge(name, env, false);
        if (env.ok && env.data) {
          try { render(env.data, env); } catch (err) { console.error(name, "render failed", err); }
        } else {
          renderEmpty(name, env);
        }
      } catch (err) {
        if (/HTTP 404/.test(err.message) && onMissing) { onMissing(); return; }  // source not configured
        state.failures += 1;
        console.warn(name, err.message);
        setBadge(name, { ok: true, stale: false }, true);
        if (state.failures > 40) location.reload(); // renderer or server wedged for a long time
      }
      const jitter = Math.random() * 5000;
      timer = setTimeout(tick, intervalSeconds * 1000 + jitter);
    }
    tick();
    return () => clearTimeout(timer);
  }

  // ---------- clock, countdowns, schedule --------------------------------------------------
  let lastDay = "";
  function startClock() {
    function draw() {
      const now = new Date();
      const get = fmtParts(now, { hour: "numeric", minute: "2-digit" });
      $("clock-time").textContent = `${get("hour")}:${get("minute")}`;
      $("clock-ampm").textContent = get("dayPeriod") || "";
      $("clock-date").textContent = new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric", timeZone: tz() }).format(now);
      const day = todayISO();
      if (day !== lastDay) { lastDay = day; renderCountdowns(); }
      applySchedule();
      checkDailyReload(now);
    }
    draw();
    setInterval(draw, 1000);
  }

  function renderCountdowns() {
    const box = $("countdowns");
    const list = cfg("countdowns", []);
    const today = new Date(todayISO() + "T00:00:00Z").getTime();
    const items = list
      .map((c) => ({ ...c, days: Math.round((new Date(c.date + "T00:00:00Z").getTime() - today) / 86400000) }))
      .filter((c) => c.days >= 0)
      .slice(0, 3);
    box.classList.toggle("hidden", items.length === 0);
    box.innerHTML = items.map((c) => {
      const n = c.days === 0 ? '<span class="n today">Today!</span>' : `<span class="n${c.days > 999 ? " big" : ""}">${c.days}</span>`;
      const sub = c.days === 0 ? "" : c.days === 1 ? "day to go" : "days until";
      return `<div class="cd">${n}<span class="t">${escapeHTML(c.icon ? c.icon + " " : "")}${escapeHTML(c.title)}<small>${sub}</small></span></div>`;
    }).join("");
  }

  let reloadArmed = true;
  function checkDailyReload(now) {
    const at = cfg("reload_at", "03:30");
    const hm = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: tz() }).format(now);
    const upHours = (Date.now() - state.startedAt) / 3.6e6;
    if ((hm === at && reloadArmed && upHours > 0.1) || upHours > 26) {
      reloadArmed = false;
      location.reload();
    }
    if (hm !== at) reloadArmed = true;
  }

  /** Dim in the evening and go black during screen-off hours (visual fallback if HDMI control fails). */
  function minutesOf(hm) { const m = /^(\d{1,2}):(\d{2})$/.exec(hm || ""); return m ? Number(m[1]) * 60 + Number(m[2]) : null; }
  function inWindow(nowMin, fromMin, toMin) {
    if (fromMin == null || toMin == null) return false;
    return fromMin < toMin ? nowMin >= fromMin && nowMin < toMin : nowMin >= fromMin || nowMin < toMin;
  }
  function applySchedule() {
    const d = cfg("display", {});
    const hm = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: tz() }).format(new Date());
    const nowMin = minutesOf(hm);
    const off = inWindow(nowMin, minutesOf(d.screen_off), minutesOf(d.screen_on));
    const dim = !off && inWindow(nowMin, minutesOf(d.dim_from), minutesOf(d.screen_on || "06:00"));
    const overlay = $("dim-overlay");
    overlay.style.opacity = off ? "1" : dim ? String(Math.min(0.9, Number(d.dim_level) || 0.5)) : "0";
    document.body.classList.toggle("screen-off", off);
  }

  // ---------- alerts -------------------------------------------------------------------------
  function renderAlerts(d) {
    const banner = $("alert-banner");
    const top = d.top;
    document.body.classList.toggle("alert-extreme", !!top && top.severity === "Extreme");
    if (!top) { banner.classList.add("hidden"); hideTakeover(); return; }
    banner.className = "alert sev-" + (top.severity || "unknown").toLowerCase();
    $("alert-event").textContent = top.event + (d.count > 1 ? ` +${d.count - 1}` : "");
    $("alert-text").textContent = (top.headline || top.description || "").replace(/\s+by NWS.*$/i, "");
    $("alert-until").textContent = top.ends ? "until " + fmtTime(new Date(top.ends)) : "";
    if (d.takeover) maybeTakeover(d.takeover); else hideTakeover();
  }

  // ---------- alert takeover -----------------------------------------------------------------
  const takeover = { key: null, timer: null, shown: false, dismissed: new Set(), map: null, layers: new Map(), template: "" };
  function takeoverKey(a) { return `${a.event}|${a.area}|${(a.ends || "").slice(0, 13)}`; }
  function maybeTakeover(a) {
    if (!cfg("takeover.takeover", true)) return;
    const key = takeoverKey(a);
    if (takeover.dismissed.has(key)) return;
    if (takeover.shown && takeover.key === key) return;
    showTakeover(a, key);
  }
  function showTakeover(a, key) {
    takeover.key = key; takeover.shown = true;
    const box = $("takeover");
    box.className = "takeover sev-" + (a.severity || "severe").toLowerCase();
    $("takeover-event").textContent = a.event;
    $("takeover-until").textContent = a.ends ? "until " + fmtTime(new Date(a.ends)) + (a.sender ? " · " + a.sender : "") : a.sender || "";
    $("takeover-headline").textContent = (a.headline || "").replace(/\s+by NWS.*$/i, "");
    $("takeover-desc").textContent = (a.description || "").replace(/\s+/g, " ");
    $("takeover-instr").textContent = a.instruction || "";
    $("takeover-instr").classList.toggle("hidden", !a.instruction);
    $("takeover-area").textContent = a.area || "";
    box.classList.remove("hidden");
    chronPause(true);
    setupTakeoverMap();
    clearTimeout(takeover.timer);
    const minutes = Number(cfg("takeover.takeover_minutes", 10)) || 10;
    takeover.timer = setTimeout(() => dismissTakeover(false), minutes * 60000);
    if (cfg("takeover.takeover_sound", true)) chime();
  }
  function hideTakeover() {
    if (!takeover.shown) return;
    takeover.shown = false;
    $("takeover").classList.add("hidden");
    clearTimeout(takeover.timer);
    chronPause(false);
  }
  function dismissTakeover(byUser) {
    if (takeover.key) takeover.dismissed.add(takeover.key);  // don't re-show the same alert
    hideTakeover();
  }
  function setupTakeoverMap() {
    if (!window.L || !radar.map) return;
    const center = radar.map.getCenter();
    if (!takeover.map) {
      takeover.map = L.map("takeover-map", { zoomControl: false, attributionControl: false, dragging: false, scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false, keyboard: false, touchZoom: false, fadeAnimation: false }).setView(center, Math.min(8, radar.map.getZoom() + 1));
      L.tileLayer(radar.baseTemplate, { subdomains: "abcd", maxZoom: 12 }).addTo(takeover.map);
      takeover.map.createPane("labels").style.zIndex = 450;
      if (radar.labelsTemplate) L.tileLayer(radar.labelsTemplate, { pane: "labels", maxZoom: 12 }).addTo(takeover.map);
      L.marker(center, { icon: L.divIcon({ className: "radar-here", iconSize: [14, 14] }), interactive: false }).addTo(takeover.map);
    }
    syncTakeoverLayers();
    setTimeout(() => takeover.map.invalidateSize(), 300);
  }
  function syncTakeoverLayers() {
    if (!takeover.map) return;
    const wanted = new Set(radar.order.map((f) => f.path));
    for (const [path, layer] of takeover.layers) if (!wanted.has(path) || takeover.template !== radar.template) { takeover.map.removeLayer(layer); takeover.layers.delete(path); }
    takeover.template = radar.template;
    for (const f of radar.order) if (!takeover.layers.has(f.path)) {
      const layer = L.tileLayer(radar.template.replace("{path}", f.path), { opacity: 0, maxNativeZoom: radar.maxNative || 7, maxZoom: 12, updateWhenIdle: false });
      layer.addTo(takeover.map); takeover.layers.set(f.path, layer);
    }
  }
  function chime() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.35, 0.7].forEach((t) => {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type = "sine"; o.frequency.value = 880; o.connect(g); g.connect(ctx.destination);
        g.gain.setValueAtTime(0.0001, ctx.currentTime + t); g.gain.exponentialRampToValueAtTime(0.3, ctx.currentTime + t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + t + 0.3);
        o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.32);
      });
    } catch (e) { /* no audio device */ }
  }

  // ---------- ChronAlert embed ---------------------------------------------------------------
  const chron = { url: "", mode: "off", timer: null, showing: false, paused: false, full: false };
  function chronUrl() { return cfg("chronalert.url", "") || `http://${location.hostname}:8420/`; }
  function chronPause(on) { chron.paused = on; if (on && chron.showing) chronShowPhotos(); }
  async function chronReachable() {
    // Ask the server whether ChronAlert answers, so the slideshow never swaps to a black frame.
    try { const r = await fetch("/api/chronalert/status", { cache: "no-store" }); return (await r.json()).reachable === true; }
    catch (e) { return true; }  // can't tell: try anyway
  }
  async function chronShowMap() {
    if (chron.paused || document.body.classList.contains("screen-off")) { chron.timer = setTimeout(chronShowMap, 30000); return; }
    if (!(await chronReachable())) { chron.timer = setTimeout(chronShowMap, 60000); return; }
    const f = $("chron-frame");
    if (!f.src) f.src = chronUrl();
    f.classList.remove("hidden"); requestAnimationFrame(() => f.classList.add("visible"));
    chron.showing = true;
    chron.timer = setTimeout(chronShowPhotos, (Number(cfg("chronalert.show_seconds", 90)) || 90) * 1000);
  }
  function chronShowPhotos() {
    const f = $("chron-frame");
    f.classList.remove("visible"); setTimeout(() => { if (!chron.showing) f.classList.add("hidden"); }, 1100);
    chron.showing = false;
    clearTimeout(chron.timer);
    chron.timer = setTimeout(chronShowMap, (Number(cfg("chronalert.photo_seconds", 180)) || 180) * 1000);
  }
  function chronToggleFull() {
    if (cfg("chronalert.open_mode", "iframe") === "window") { window.open(chronUrl(), "chronalert"); return; }
    chron.full = !chron.full;
    const box = $("chron-full");
    if (chron.full) { $("chron-full-frame").src = chronUrl(); box.classList.remove("hidden"); }
    else { box.classList.add("hidden"); $("chron-full-frame").src = "about:blank"; }
  }
  function startChron() {
    chron.mode = cfg("chronalert.mode", "off");
    if (chron.mode === "off") return;
    $("chron-btn").classList.remove("hidden");
    $("chron-btn").addEventListener("click", chronToggleFull);
    $("chron-close").addEventListener("click", chronToggleFull);
    if (chron.mode === "rotate") chron.timer = setTimeout(chronShowMap, (Number(cfg("chronalert.photo_seconds", 180)) || 180) * 1000);
  }

  // ---------- weather ------------------------------------------------------------------------
  function renderWeather(d) {
    const c = d.current || {};
    $("weather-place").textContent = d.location || "Weather";
    $("weather-icon").innerHTML = window.weatherIcon(c.icon, c.is_day);
    $("weather-temp").textContent = c.temp ?? "--";
    $("weather-unit").textContent = (d.units && d.units.temp) || "°";
    $("weather-label").textContent = c.label || "";
    const wind = c.wind != null ? `Wind ${c.wind} ${d.units.wind}${c.wind_dir ? " " + c.wind_dir : ""}` : "";
    $("weather-detail").innerHTML = [c.feels_like != null ? `Feels like ${c.feels_like}°` : "", c.humidity != null ? `Humidity ${c.humidity}%` : "", wind]
      .filter(Boolean).map(escapeHTML).join("<br>");
    const t = d.today;
    if (t) {
      const sr = fmtLocalClock(t.sunrise);
      const ss = fmtLocalClock(t.sunset);
      $("weather-today").textContent = `Today ${t.hi ?? "--"}° / ${t.lo ?? "--"}° · ${t.label}${t.precip_pct ? ` · ${t.precip_pct}% rain` : ""}`;
    }
    const chips = [];
    if (t && t.sunrise) chips.push(`<span class="chip">☀ ${escapeHTML(fmtLocalClock(t.sunrise))} – ${escapeHTML(fmtLocalClock(t.sunset))}</span>`);
    if (t && t.uv) chips.push(`<span class="chip">UV ${escapeHTML(Math.round(t.uv.index))} ${escapeHTML(t.uv.label)}</span>`);
    if (d.air) chips.push(`<span class="chip"><i class="dot" style="background:${escapeHTML(d.air.color)}"></i>Air ${escapeHTML(d.air.aqi)} ${escapeHTML(d.air.label)}</span>`);
    if (d.moon) chips.push(`<span class="chip" title="${escapeHTML(d.moon.name)}">${window.moonIcon(d.moon.phase)}${escapeHTML(d.moon.illumination)}%</span>`);
    $("weather-chips").innerHTML = chips.join("");
    $("hourly").innerHTML = (d.hourly || []).map((h) => `
      <li>
        <span class="h">${escapeHTML(fmtLocalClock(h.time, true))}</span>
        <span class="icon">${window.weatherIcon(h.icon, h.is_day)}</span>
        <span class="t">${h.temp ?? "--"}°</span>
        <span class="p">${h.precip_pct >= 20 ? h.precip_pct + "%" : ""}</span>
      </li>`).join("");
    $("hourly").classList.toggle("hidden", !(d.hourly || []).length);
    const list = $("forecast");
    list.innerHTML = (d.daily || []).slice(0, 5).map((day) => `
      <li>
        <span class="day">${escapeHTML(weekdayShort(day.date))}</span>
        <span class="icon">${window.weatherIcon(day.icon, true)}</span>
        <span class="label">${escapeHTML(day.label)}${day.precip_pct >= 20 ? `<span class="pct">${day.precip_pct}%</span>` : ""}</span>
        <span class="temps">${day.hi ?? "--"}°<span class="lo">${day.lo ?? "--"}°</span></span>
      </li>`).join("");
  }

  // ---------- radar --------------------------------------------------------------------------
  const radar = { map: null, base: null, layers: new Map(), order: [], index: 0, timer: null, template: "" };
  function renderRadar(d) {
    if (!window.L) return;
    if (!radar.map) {
      radar.map = L.map("map", {
        zoomControl: false, attributionControl: false, dragging: false, scrollWheelZoom: false,
        doubleClickZoom: false, boxZoom: false, keyboard: false, touchZoom: false, fadeAnimation: false,
      }).setView(d.center, d.zoom);
      radar.baseTemplate = d.basemap_template; radar.labelsTemplate = d.labels_template || ""; radar.maxNative = d.max_native_zoom || 7;
      radar.base = L.tileLayer(d.basemap_template, { subdomains: "abcd", maxZoom: 12 }).addTo(radar.map);
      radar.map.createPane("labels").style.zIndex = 450;  // city names and borders sit above the radar
      if (d.labels_template) L.tileLayer(d.labels_template, { pane: "labels", maxZoom: 12 }).addTo(radar.map);
      L.marker(d.center, { icon: L.divIcon({ className: "radar-here", iconSize: [14, 14] }), interactive: false }).addTo(radar.map);
      $("radar-attrib").textContent = [d.attribution, d.basemap_attribution].filter(Boolean).join(" · ");
      setTimeout(() => radar.map.invalidateSize(), 300);
      if (takeover.shown && !takeover.map) setupTakeoverMap();  // an alert arrived before the radar did
    }
    if (radar.template !== d.tile_template) {  // provider changed: drop everything
      radar.layers.forEach((l) => radar.map.removeLayer(l));
      radar.layers.clear();
      radar.template = d.tile_template;
    }
    const wanted = new Set(d.frames.map((f) => f.path));
    for (const [path, layer] of radar.layers) {
      if (!wanted.has(path)) { radar.map.removeLayer(layer); radar.layers.delete(path); }
    }
    for (const f of d.frames) {
      if (!radar.layers.has(f.path)) {
        const url = d.tile_template.replace("{path}", f.path);
        const layer = L.tileLayer(url, { opacity: 0, maxNativeZoom: d.max_native_zoom || 7, maxZoom: 12, updateWhenIdle: false, keepBuffer: 2 });
        layer.addTo(radar.map);
        radar.layers.set(f.path, layer);
      }
    }
    radar.order = d.frames.map((f) => ({ path: f.path, time: f.time }));
    radar.index = Math.max(0, radar.order.length - 1);
    if (takeover.map) syncTakeoverLayers();
    if (!radar.timer) startRadarLoop();
  }
  function startRadarLoop() {
    const frameMs = cfg("radar.frame_ms", 600);
    function step() {
      const n = radar.order.length;
      if (!n || document.body.classList.contains("screen-off")) { radar.timer = setTimeout(step, 2000); return; }
      radar.index = (radar.index + 1) % n;
      radar.order.forEach((f, i) => {
        const layer = radar.layers.get(f.path);
        if (layer) layer.setOpacity(i === radar.index ? 0.85 : 0);
        const t = takeover.layers.get(f.path);
        if (t) t.setOpacity(i === radar.index ? 0.85 : 0);
      });
      const f = radar.order[radar.index];
      $("radar-time").textContent = fmtTime(new Date(f.time * 1000));
      if (takeover.shown) $("takeover-time").textContent = $("radar-time").textContent;
      radar.timer = setTimeout(step, radar.index === n - 1 ? frameMs * 4 : frameMs);
    }
    step();
  }

  // ---------- stocks & sports ----------------------------------------------------------------
  function renderStocks(d) {
    $("market-state").textContent = d.market_open ? "· market open" : "· market closed";
    $("quotes").dataset.hasData = "1";
    $("quotes").innerHTML = (d.quotes || []).map((q) => {
      const dir = q.change > 0 ? "up" : q.change < 0 ? "down" : "flat";
      const sign = q.change > 0 ? "+" : "";
      return `<div class="quote ${dir}">
        <div class="sym">${escapeHTML(q.symbol)}</div>
        <div class="name">${escapeHTML(q.name)}</div>
        <div class="price">${q.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
        <div class="chg">${sign}${q.change_pct.toFixed(2)}%</div>
        <div class="abs">${sign}${q.change.toFixed(2)}</div>
      </div>`;
    }).join("");
  }

  function gameWhen(g) {
    if (!g || !g.date) return "";
    const date = new Date(g.date);
    const day = new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone: tz() }).format(date);
    return g.time_tbd ? `${day} · TBD` : `${day} · ${fmtShortTime(date)}`;
  }
  function renderSports(d) {
    const t = (d.teams || [])[0];
    const tile = $("sports");
    if (!t) { tile.classList.add("hidden"); return; }
    tile.classList.remove("hidden");
    tile.style.setProperty("--team", t.color || "var(--accent)");
    $("markets-title").textContent = "Markets & Sports";
    const lines = [];
    if (t.live) {
      lines.push(`<div class="line"><span class="k">Live</span><span class="live">${t.live.home ? "vs" : "at"} ${escapeHTML(t.live.opponent)} · ${t.live.score_us ?? 0}–${t.live.score_them ?? 0} · ${escapeHTML(t.live.clock || "")}</span></div>`);
    } else if (t.next) {
      lines.push(`<div class="line"><span class="k">Next</span><span>${t.next.home ? "vs" : "at"} ${escapeHTML(t.next.opponent)} · ${escapeHTML(gameWhen(t.next))}${t.next.tv ? " · " + escapeHTML(t.next.tv) : ""}</span></div>`);
    }
    if (t.last) {
      lines.push(`<div class="line"><span class="k">Last</span><span><span class="${t.last.won ? "w" : "l"}">${escapeHTML(t.last.result)}</span> ${t.last.home ? "vs" : "at"} ${escapeHTML(t.last.opponent)}</span></div>`);
    }
    tile.innerHTML = `
      <div class="head">${t.logo ? `<img src="${escapeHTML(t.logo)}" alt="" onerror="this.remove()">` : ""}
        <div><div class="team">${escapeHTML(t.short || t.name)}</div><div class="record">${escapeHTML([t.record, t.standing].filter(Boolean).join(" · "))}</div></div>
      </div>${lines.join("")}`;
  }

  // ---------- calendar -----------------------------------------------------------------------
  function renderCalendar(d) {
    const max = cfg("calendar.max_events", 12);
    let shown = 0;
    const html = [];
    for (const day of d.days || []) {
      const isToday = day.label === "Today";
      if (!isToday && !day.events.length) continue;
      if (shown >= max) break;
      const date = new Date(day.date + "T12:00:00");
      const dateStr = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(date);
      const rows = day.events.slice(0, max - shown).map((e) => {
        const when = e.all_day ? "All day" : fmtShortTime(new Date(e.start));
        return `<div class="event" style="--cal:${escapeHTML(e.color || "transparent")}"><span class="when">${escapeHTML(when)}</span><span class="what">${escapeHTML(e.title)}${e.location ? `<div class="where">${escapeHTML(e.location)}</div>` : ""}</span></div>`;
      });
      shown += day.events.length;
      html.push(`<div class="day${isToday ? " today" : ""}"><div class="day-head"><span>${escapeHTML(day.label)}</span><span>${dateStr}</span></div>${rows.join("") || '<div class="none">Nothing scheduled</div>'}</div>`);
    }
    $("agenda").dataset.hasData = "1";
    $("agenda").innerHTML = html.join("") || '<div class="none">Nothing coming up</div>';
    const cals = d.calendars || [];
    $("cal-legend").innerHTML = cals.length > 1 ? cals.map((c) => `<span><i style="background:${escapeHTML(c.color)}"></i>${escapeHTML(c.name)}${c.ok === false ? " ⚠" : ""}</span>`).join("") : "";
  }

  // ---------- news ticker --------------------------------------------------------------------
  const ticker = { pending: null, track: null };
  function buildTicker(headlines) {
    const items = headlines.map((h) => `<span class="ticker-item"><span class="src">${escapeHTML(h.source)}</span>${escapeHTML(h.title)}</span>`).join("");
    const track = ticker.track;
    track.innerHTML = items + items;  // duplicated so the loop is seamless at -50%
    const viewport = track.parentElement.clientWidth;
    const half = track.scrollWidth / 2;
    // keep a constant speed of ~110 px/s (in CSS px at 1920 wide); short lists still scroll
    const pxPerSecond = 0.0573 * window.innerWidth;
    track.style.animationDuration = `${Math.max(20, half / pxPerSecond)}s`;
    if (half < viewport) track.style.paddingRight = `${viewport - half}px`;
  }
  function renderNews(d) {
    const headlines = d.headlines || [];
    if (!headlines.length) return;
    if (!ticker.track) {
      ticker.track = $("ticker-track");
      ticker.track.addEventListener("animationiteration", () => {
        if (ticker.pending) { buildTicker(ticker.pending); ticker.pending = null; }
      });
      buildTicker(headlines);
    } else {
      ticker.pending = headlines;  // swap in at the next seamless loop point
    }
  }

  // ---------- photos -------------------------------------------------------------------------
  const slideshow = { list: [], index: -1, front: "a", timer: null, seconds: 20 };
  function renderPhotos(d) {
    const list = d.photos || [];
    slideshow.seconds = Number(d.seconds_per_photo) || slideshow.seconds;
    $("photo-empty").classList.toggle("hidden", list.length > 0);
    const changed = list.length !== slideshow.list.length || list.some((p, i) => p.url !== slideshow.list[i].url);
    if (changed) {
      slideshow.list = list;
      slideshow.index = -1;
      if (!slideshow.timer) nextPhoto();
    }
  }
  function nextPhoto() {
    clearTimeout(slideshow.timer);
    const list = slideshow.list;
    if (!list.length || document.body.classList.contains("screen-off")) { slideshow.timer = setTimeout(nextPhoto, 5000); return; }
    slideshow.index = (slideshow.index + 1) % list.length;
    const url = list[slideshow.index].url;
    const backId = slideshow.front === "a" ? "photo-b" : "photo-a";
    const frontId = slideshow.front === "a" ? "photo-a" : "photo-b";
    const img = new Image();
    img.onload = () => {
      $(backId).src = url;
      $(backId).classList.add("visible");
      $(frontId).classList.remove("visible");
      slideshow.front = slideshow.front === "a" ? "b" : "a";
    };
    img.onerror = () => console.warn("photo failed", url);
    img.src = url;
    slideshow.timer = setTimeout(nextPhoto, slideshow.seconds * 1000);
  }

  // ---------- now playing --------------------------------------------------------------------
  const np = { progress: 0, duration: 0, at: 0, playing: false, timer: null };
  function renderNowPlaying(d) {
    const card = $("now-playing");
    np.playing = !!d.playing;
    if (!d.playing) { card.classList.add("hidden"); return; }
    card.classList.remove("hidden");
    if ($("np-art").src !== d.art_url) { $("np-art").src = d.art_url || ""; }
    $("np-art").classList.toggle("hidden", !d.art_url);
    $("np-title").textContent = d.title || "";
    $("np-artist").textContent = d.artist || "";
    np.progress = Number(d.progress_ms) || 0; np.duration = Number(d.duration_ms) || 0; np.at = Date.now();
    if (!np.timer) np.timer = setInterval(() => {
      if (!np.playing || !np.duration) return;
      const pos = Math.min(np.duration, np.progress + (Date.now() - np.at));
      $("np-progress").style.width = `${(pos / np.duration) * 100}%`;
    }, 1000);
  }

  // ---------- to-do + notes ------------------------------------------------------------------
  const todoState = { items: 0, notes: false };
  function updateTodoVisibility() {
    const enabled = cfg("panels.todo", true) !== false;
    document.body.classList.toggle("has-todo", enabled && (todoState.items > 0 || todoState.notes));
  }
  function renderTodo(d) {
    const max = Number(d.max_items) || 8;
    const items = d.items || [];
    todoState.items = items.length;
    const list = $("todo-list");
    const undone = items.filter((i) => !i.done);
    const done = items.filter((i) => i.done);
    const shown = undone.slice(0, max).concat(done.slice(0, Math.max(0, max - undone.length)));
    list.innerHTML = shown.map((i) => `<li class="${i.done ? "done" : ""}"><span class="box"></span><span>${escapeHTML(i.text)}</span></li>`).join("")
      + (undone.length > max ? `<li><span></span><span class="more">+${undone.length - max} more</span></li>` : "");
    updateTodoVisibility();
  }
  function renderNotes(d) {
    const text = (d.text || "").trim();
    todoState.notes = !!text;
    $("notes").textContent = text;
    $("notes").classList.toggle("hidden", !text);
    updateTodoVisibility();
  }

  // ---------- settings gear + cursor -------------------------------------------------------------
  function startInputWatch() {
    let timer = null;
    const show = () => {
      document.body.classList.add("show-cursor");
      clearTimeout(timer);
      timer = setTimeout(() => document.body.classList.remove("show-cursor"), 5000);
    };
    window.addEventListener("mousemove", show, { passive: true });
    window.addEventListener("touchstart", show, { passive: true });
    window.addEventListener("keydown", (e) => {
      if (e.key === "s" || e.key === "S") location.href = "/manage?kiosk=1";
      if (e.key === "d" || e.key === "D") switchToDesktop();
      if ((e.key === "c" || e.key === "C") && chron.mode !== "off") chronToggleFull();
      if (e.key === "Escape") { if (chron.full) chronToggleFull(); if (takeover.shown) dismissTakeover(true); }
    });
    $("desktop-btn").addEventListener("click", switchToDesktop);
    $("takeover-dismiss").addEventListener("click", () => dismissTakeover(true));
  }
  async function switchToDesktop() {
    if (!window.confirm("Close the dashboard and use the Pi as a computer? Open it again from the desktop icon, the app menu, or the settings page on your phone.")) return;
    try {
      const headers = { "Content-Type": "application/json" };
      const resp = await fetch("/api/display/desktop", { method: "POST", headers });
      if (resp.status === 401) { location.href = "/manage?kiosk=1#system"; return; }  // PIN set: do it from the settings page
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    } catch (err) { console.warn("desktop switch failed", err); alert("Could not switch: " + err.message + ". Press F11 for a normal window, or Alt+F4 to close the dashboard."); }
  }

  // ---------- config, panels, setup note ------------------------------------------------------
  function applyPanels() {
    const panels = cfg("panels", {});
    for (const [name, on] of Object.entries(panels)) document.body.classList.toggle("no-" + name, on === false);
    if (!cfg("sports_enabled", false)) $("sports").classList.add("hidden");
  }
  function showSetupNote() {
    const missing = cfg("setup_needed", []);
    const note = $("setup-note");
    if (!missing.length || !cfg("manage", false)) { note.classList.add("hidden"); return; }
    note.textContent = `Finish setup from your phone: http://${location.host}/manage`;
    note.classList.remove("hidden");
  }
  async function watchConfigVersion() {
    try {
      const c = await getJSON("/api/config");
      if (state.configVersion != null && c.config_version !== state.configVersion) location.reload();
      state.configVersion = c.config_version;
    } catch (err) { /* transient */ }
    setTimeout(watchConfigVersion, 60000);
  }

  // ---------- boot ---------------------------------------------------------------------------
  async function boot() {
    try { state.config = await getJSON("/api/config"); state.configVersion = state.config.config_version; } catch (err) { console.warn("config", err); }
    const iv = cfg("intervals_seconds", {});
    const every = (name, fallback) => Math.max(30, Math.min(Number(iv[name]) || fallback, fallback));
    applyPanels();
    showSetupNote();
    startClock();
    renderCountdowns();
    startWidget("weather", every("weather", 300), renderWeather);
    startWidget("alerts", every("alerts", 300), renderAlerts, () => $("alert-banner").classList.add("hidden"));
    startWidget("radar", every("radar", 300), renderRadar);
    startWidget("stocks", 60, renderStocks);
    startWidget("sports", every("sports", 300), renderSports, () => $("sports").classList.add("hidden"));
    startWidget("calendar", every("calendar", 300), renderCalendar);
    startWidget("news", every("news", 600), renderNews);
    startWidget("photos", every("photos", 300), renderPhotos);
    if (cfg("panels.todo", true) !== false) {
      startWidget("todo", 30, renderTodo, () => {});
      startWidget("notes", 30, renderNotes, () => {});
    }
    if (cfg("now_playing.provider", "off") !== "off" && cfg("panels.nowplaying", true) !== false) {
      startWidget("nowplaying", Number(cfg("now_playing.refresh_seconds", 10)) || 10, renderNowPlaying, () => $("now-playing").classList.add("hidden"));
    }
    startInputWatch();
    startChron();
    setTimeout(watchConfigVersion, 60000);
    window.addEventListener("resize", () => { if (radar.map) radar.map.invalidateSize(); });
  }
  document.addEventListener("DOMContentLoaded", boot);
})();
