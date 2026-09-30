/* Watcher Dashboard front end. Polls /api/* and renders each panel. No build step, no frameworks. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const state = { config: null, failures: 0, startedAt: Date.now() };

  // ---------- helpers ----------------------------------------------------------------------
  async function getJSON(path) {
    const resp = await fetch(path, { cache: "no-store" });
    if (!resp.ok) throw new Error(`${path} -> HTTP ${resp.status}`);
    return resp.json();
  }

  function tz() { return (state.config && state.config.timezone) || undefined; }
  function hour12() { return !(state.config && state.config.clock_24h); }

  function fmtTime(date) {
    return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", hour12: hour12(), timeZone: tz() }).format(date);
  }
  function fmtShortTime(date) {
    // "9 AM", "12:30 PM" — compact for agenda rows
    const parts = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", hour12: hour12(), timeZone: tz() }).formatToParts(date);
    const get = (t) => (parts.find((p) => p.type === t) || {}).value || "";
    const minute = get("minute");
    const ampm = get("dayPeriod");
    return `${get("hour")}${minute === "00" && hour12() ? "" : ":" + minute}${ampm ? " " + ampm : ""}`;
  }
  /** Open-Meteo sends local wall-clock times like "2026-09-30T07:23" (no zone). Format them as-is. */
  function fmtLocalClock(localIso) {
    const m = /T(\d{2}):(\d{2})/.exec(localIso || "");
    if (!m) return "";
    let h = Number(m[1]);
    const min = m[2];
    if (!hour12()) return `${m[1]}:${min}`;
    const ampm = h >= 12 ? "PM" : "AM";
    h = h % 12 || 12;
    return `${h}:${min} ${ampm}`;
  }
  function weekdayShort(isoDate) {
    const d = new Date(isoDate + "T12:00:00");
    return new Intl.DateTimeFormat("en-US", { weekday: "short" }).format(d);
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

  /** Friendly in-panel hints for the two sources that need something from the user. */
  const HINTS = {
    calendar: { needle: "OUTLOOK_ICS_URL", text: "Add your Outlook calendar link (OUTLOOK_ICS_URL) to the .env file on the Pi, then restart the dashboard service." },
    stocks: { needle: "FINNHUB_API_KEY", text: "Add a free Finnhub key (FINNHUB_API_KEY) to the .env file on the Pi, then restart the dashboard service." },
  };
  function renderEmpty(name, env) {
    const hint = HINTS[name];
    const target = name === "calendar" ? $("agenda") : name === "stocks" ? $("quotes") : null;
    if (!target || target.dataset.hasData) return;
    const msg = hint && (env.error || "").includes(hint.needle) ? hint.text : env.error ? "Waiting for data…" : "Loading…";
    target.innerHTML = `<div class="muted hint">${escapeHTML(msg)}</div>`;
  }

  /** Poll one endpoint forever. The renderer only runs when the server has data. */
  function startWidget(name, intervalSeconds, render) {
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

  // ---------- clock --------------------------------------------------------------------------
  function startClock() {
    function draw() {
      const now = new Date();
      const parts = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", hour12: hour12(), timeZone: tz() }).formatToParts(now);
      const get = (t) => (parts.find((p) => p.type === t) || {}).value || "";
      $("clock-time").textContent = `${get("hour")}:${get("minute")}`;
      $("clock-ampm").textContent = get("dayPeriod") || "";
      $("clock-date").textContent = new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric", timeZone: tz() }).format(now);
      checkDailyReload(now);
    }
    draw();
    setInterval(draw, 1000);
  }

  let reloadArmed = true;
  function checkDailyReload(now) {
    const at = (state.config && state.config.reload_at) || "03:30";
    const hm = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: tz() }).format(now);
    const upHours = (Date.now() - state.startedAt) / 3.6e6;
    if ((hm === at && reloadArmed && upHours > 0.1) || upHours > 26) {
      reloadArmed = false;
      location.reload();
    }
    if (hm !== at) reloadArmed = true;
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
      $("weather-today").textContent = `Today ${t.hi ?? "--"}° / ${t.lo ?? "--"}° · ${t.label}${t.precip_pct ? ` · ${t.precip_pct}% rain` : ""}${sr ? ` · ☀ ${sr} – ${ss}` : ""}`;
    }
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
      radar.base = L.tileLayer(d.basemap_template, { subdomains: "abcd", maxZoom: 12 }).addTo(radar.map);
      radar.map.createPane("labels").style.zIndex = 450;  // city names and borders sit above the radar
      if (d.labels_template) L.tileLayer(d.labels_template, { pane: "labels", maxZoom: 12 }).addTo(radar.map);
      L.marker(d.center, { icon: L.divIcon({ className: "radar-here", iconSize: [14, 14] }), interactive: false }).addTo(radar.map);
      $("radar-attrib").textContent = [d.attribution, d.basemap_attribution].filter(Boolean).join(" · ");
      setTimeout(() => radar.map.invalidateSize(), 300);
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
    if (!radar.timer) startRadarLoop();
  }
  function startRadarLoop() {
    const frameMs = (state.config && state.config.radar && state.config.radar.frame_ms) || 600;
    function step() {
      const n = radar.order.length;
      if (!n) { radar.timer = setTimeout(step, frameMs); return; }
      radar.index = (radar.index + 1) % n;
      radar.order.forEach((f, i) => {
        const layer = radar.layers.get(f.path);
        if (layer) layer.setOpacity(i === radar.index ? 0.85 : 0);
      });
      const f = radar.order[radar.index];
      $("radar-time").textContent = fmtTime(new Date(f.time * 1000)) + (radar.index === n - 1 ? "" : "");
      radar.timer = setTimeout(step, radar.index === n - 1 ? frameMs * 4 : frameMs);
    }
    step();
  }

  // ---------- stocks -------------------------------------------------------------------------
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
        <div class="chg">${sign}${q.change.toFixed(2)} (${sign}${q.change_pct.toFixed(2)}%)</div>
      </div>`;
    }).join("");
  }

  // ---------- calendar -----------------------------------------------------------------------
  function renderCalendar(d) {
    const max = (state.config && state.config.calendar && state.config.calendar.max_events) || 12;
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
        return `<div class="event"><span class="when">${escapeHTML(when)}</span><span class="what">${escapeHTML(e.title)}${e.location ? `<div class="where">${escapeHTML(e.location)}</div>` : ""}</span></div>`;
      });
      shown += day.events.length;
      html.push(`<div class="day${isToday ? " today" : ""}"><div class="day-head"><span>${escapeHTML(day.label)}</span><span>${dateStr}</span></div>${rows.join("") || '<div class="none">Nothing scheduled</div>'}</div>`);
    }
    $("agenda").dataset.hasData = "1";
    $("agenda").innerHTML = html.join("") || '<div class="none">Nothing coming up</div>';
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
    if (!list.length) { slideshow.timer = setTimeout(nextPhoto, 5000); return; }
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

  // ---------- boot ---------------------------------------------------------------------------
  async function boot() {
    try { state.config = await getJSON("/api/config"); } catch (err) { console.warn("config", err); }
    const iv = (state.config && state.config.intervals_seconds) || {};
    const every = (name, fallback) => Math.max(30, Math.min(Number(iv[name]) || fallback, fallback));
    startClock();
    startWidget("weather", every("weather", 300), renderWeather);
    startWidget("radar", every("radar", 300), renderRadar);
    startWidget("stocks", 60, renderStocks);
    startWidget("calendar", every("calendar", 300), renderCalendar);
    startWidget("news", every("news", 600), renderNews);
    startWidget("photos", every("photos", 300), renderPhotos);
    window.addEventListener("resize", () => { if (radar.map) radar.map.invalidateSize(); });
  }
  document.addEventListener("DOMContentLoaded", boot);
})();
