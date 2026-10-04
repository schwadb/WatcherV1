/* Settings page: photos, to-do, notes, settings, system. Works on a phone and (with ?kiosk=1) on the TV. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const params = new URLSearchParams(location.search);
  const KIOSK = params.get("kiosk") === "1";
  let pin = sessionStorage.getItem("dashboard_pin") || "";
  let config = null;      // from /api/config
  let settings = null;    // from /api/settings

  // ---------- plumbing -----------------------------------------------------------------------
  async function api(path, opts = {}) {
    const headers = { ...(opts.headers || {}) };
    if (pin) headers["X-Pin"] = pin;
    if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
    const resp = await fetch(path, { ...opts, headers, cache: "no-store" });
    if (resp.status === 401) { showPinGate(); throw new Error("PIN required"); }
    let data = null;
    try { data = await resp.json(); } catch (e) { data = null; }
    if (!resp.ok) {
      const msg = (data && (data.errors ? data.errors.join("\n") : data.detail || data.message)) || `HTTP ${resp.status}`;
      throw new Error(msg);
    }
    return data;
  }
  let toastTimer = null;
  function toast(msg, bad) {
    const el = $("toast");
    el.textContent = msg;
    el.classList.toggle("bad", !!bad);
    el.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.add("hidden"), bad ? 6000 : 2500);
  }
  function esc(s) { return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  async function confirmAction(text) { return window.confirm(text); }

  // ---------- tabs ---------------------------------------------------------------------------
  const loaders = { photos: loadPhotos, todo: loadTodo, notes: loadNotes, settings: loadSettings, music: loadMusic, system: loadSystem };
  function showTab(name) {
    if (!loaders[name]) name = "photos";
    document.querySelectorAll(".tab").forEach((el) => el.classList.toggle("active", el.id === "tab-" + name));
    document.querySelectorAll(".tabs a").forEach((a) => a.classList.toggle("active", a.dataset.tab === name));
    loaders[name]().catch((err) => toast(err.message, true));
  }
  window.addEventListener("hashchange", () => showTab(location.hash.slice(1)));

  // ---------- PIN ----------------------------------------------------------------------------
  function showPinGate() { $("pin-gate").classList.remove("hidden"); $("pin-input").focus(); }
  $("pin-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const attempt = $("pin-input").value.trim();
    try {
      pin = attempt;
      await api("/api/pin", { method: "POST", json: { pin: attempt } });
      sessionStorage.setItem("dashboard_pin", pin);
      $("pin-gate").classList.add("hidden");
      showTab(location.hash.slice(1) || "photos");
    } catch (err) { pin = ""; toast("Wrong PIN", true); }
  });

  // ---------- photos -------------------------------------------------------------------------
  async function loadPhotos() {
    const d = await api("/api/photos/list");
    $("photo-count").textContent = d.photos.length ? `(${d.photos.length})` : "(none yet)";
    $("photo-grid").innerHTML = d.photos.map((p) => `
      <div class="thumb" data-name="${esc(p.name)}">
        ${p.thumb ? `<img src="${esc(p.thumb)}" alt="">` : ""}
        <div class="name">${esc(p.name)}</div>
        <button class="del" type="button" title="Delete">✕</button>
      </div>`).join("");
    $("photo-grid").querySelectorAll(".del").forEach((btn) => btn.addEventListener("click", async () => {
      const name = btn.parentElement.dataset.name;
      if (!(await confirmAction(`Delete ${name} from the dashboard?`))) return;
      try { await api(`/api/photos/${encodeURIComponent(name)}`, { method: "DELETE" }); toast("Deleted"); loadPhotos(); } catch (err) { toast(err.message, true); }
    }));
  }
  async function uploadFiles(files) {
    if (!files.length) return;
    const status = $("upload-status");
    status.textContent = `Uploading ${files.length} photo${files.length > 1 ? "s" : ""}…`;
    const form = new FormData();
    for (const f of files) form.append("files", f, f.name);
    try {
      const d = await api("/api/photos/upload", { method: "POST", body: form });
      const lines = [];
      if (d.saved.length) lines.push(`Added ${d.saved.length} photo${d.saved.length > 1 ? "s" : ""}. They show on the dashboard within a few seconds.`);
      for (const r of d.rejected) lines.push(`✕ ${r.name}: ${r.reason}`);
      status.innerHTML = lines.map((l) => (l.startsWith("✕") ? `<span class="bad">${esc(l)}</span>` : esc(l))).join("<br>");
      if (d.saved.length) toast("Photos added");
      loadPhotos();
    } catch (err) { status.innerHTML = `<span class="bad">${esc(err.message)}</span>`; }
    $("file-input").value = "";
  }
  $("file-input").addEventListener("change", (e) => uploadFiles([...e.target.files]));
  const dz = $("dropzone");
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("over"); }));
  dz.addEventListener("drop", (e) => uploadFiles([...e.dataTransfer.files]));

  // ---------- to-do --------------------------------------------------------------------------
  async function loadTodo() {
    const env = await api("/api/todo");
    const items = env.data.items;
    $("todo-items").innerHTML = items.map((i) => `
      <li class="${i.done ? "done" : ""}" data-id="${esc(i.id)}">
        <input type="checkbox" ${i.done ? "checked" : ""}>
        <span class="text">${esc(i.text)}</span>
        <button class="del" type="button" title="Delete">✕</button>
      </li>`).join("") || '<li class="muted">Nothing on the list.</li>';
    $("todo-items").querySelectorAll("li[data-id]").forEach((li) => {
      li.querySelector("input").addEventListener("change", async (e) => {
        try { await api(`/api/todo/${li.dataset.id}`, { method: "PATCH", json: { done: e.target.checked } }); loadTodo(); } catch (err) { toast(err.message, true); }
      });
      li.querySelector(".del").addEventListener("click", async () => {
        try { await api(`/api/todo/${li.dataset.id}`, { method: "DELETE" }); loadTodo(); } catch (err) { toast(err.message, true); }
      });
    });
  }
  $("todo-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = $("todo-input").value.trim();
    if (!text) return;
    try { await api("/api/todo", { method: "POST", json: { text } }); $("todo-input").value = ""; loadTodo(); } catch (err) { toast(err.message, true); }
  });
  $("todo-clear").addEventListener("click", async () => {
    try { await api("/api/todo", { method: "DELETE" }); loadTodo(); } catch (err) { toast(err.message, true); }
  });

  // ---------- notes --------------------------------------------------------------------------
  let notesTimer = null;
  async function loadNotes() {
    const env = await api("/api/notes");
    if (document.activeElement !== $("notes-text")) $("notes-text").value = env.data.text || "";
  }
  $("notes-text").addEventListener("input", () => {
    clearTimeout(notesTimer);
    $("notes-status").textContent = "Typing…";
    notesTimer = setTimeout(async () => {
      try { await api("/api/notes", { method: "PUT", json: { text: $("notes-text").value } }); $("notes-status").textContent = "Saved."; }
      catch (err) { $("notes-status").textContent = "Not saved: " + err.message; }
    }, 1000);
  });

  // ---------- settings -----------------------------------------------------------------------
  const PANEL_LABELS = { alerts: "Severe weather banner", radar: "Radar", stocks: "Stocks", sports: "Sports team", calendar: "Calendar", todo: "To-do & notes", news: "News ticker", photos: "Photos", nowplaying: "Now playing" };
  function setField(form, name, value) {
    const el = form.querySelector(`[name="${name}"]`);
    if (!el) return;
    if (el.type === "checkbox") el.checked = !!value; else el.value = value ?? "";
  }
  function getField(form, name) {
    const el = form.querySelector(`[name="${name}"]`);
    if (!el) return undefined;
    return el.type === "checkbox" ? el.checked : el.value;
  }
  function row(kind, data = {}) {
    const div = document.createElement("div");
    div.className = "item " + kind;
    if (kind === "cal") div.innerHTML = `<input class="name" placeholder="Name (Work)" value="${esc(data.name)}"><input class="color" type="color" value="${esc(data.color || "#5aa9ff")}"><button type="button" class="del">✕</button><input class="url" placeholder="https://… .ics link" value="${esc(data.url)}">`;
    if (kind === "stock") div.innerHTML = `<input class="sym" placeholder="SPY" value="${esc(data.sym)}" style="text-transform:uppercase"><input class="name" placeholder="Shown as (S&P 500)" value="${esc(data.name)}"><button type="button" class="del">✕</button>`;
    if (kind === "cd") div.innerHTML = `<input class="title" placeholder="Vacation" value="${esc(data.title)}"><input class="date" type="date" value="${esc(data.date)}"><input class="icon" placeholder="🎉" maxlength="4" value="${esc(data.icon)}"><button type="button" class="del">✕</button>`;
    if (kind === "feed") div.innerHTML = `<input class="name" placeholder="NPR" value="${esc(data.name)}"><input class="url" placeholder="https://… /rss.xml" value="${esc(data.url)}"><button type="button" class="del">✕</button>`;
    if (kind === "team") div.innerHTML = `${data.logo ? `<img src="${esc(data.logo)}" alt="">` : "<span></span>"}<span>${esc(data.name || data.team)} <small class="hint">${esc(data.sport)} / ${esc(data.league)} · ${esc(data.team)}</small></span><button type="button" class="del">✕</button>`;
    div.dataset.json = JSON.stringify(data);
    div.querySelector(".del").addEventListener("click", () => div.remove());
    return div;
  }
  const ADD_TARGET = { calendar: ["calendar-list", "cal"], stock: ["stock-list", "stock"], countdown: ["countdown-list", "cd"], feed: ["feed-list", "feed"] };
  document.querySelectorAll("[data-add]").forEach((btn) => btn.addEventListener("click", () => {
    const [listId, kind] = ADD_TARGET[btn.dataset.add];
    $(listId).appendChild(row(kind, {}));
  }));

  async function loadSettings() {
    settings = await api("/api/settings");
    const c = settings.config;
    const warn = $("settings-warnings");
    warn.textContent = (settings.warnings || []).join("\n");
    warn.classList.toggle("hidden", !(settings.warnings || []).length);
    $("tz-list").innerHTML = settings.timezones.map((t) => `<option value="${esc(t)}">`).join("");
    const forms = Object.fromEntries([...document.querySelectorAll("form[data-section]")].map((f) => [f.dataset.section, f]));
    const f = forms.location;
    setField(f, "location.name", c.location.name); setField(f, "location.lat", c.location.lat); setField(f, "location.lon", c.location.lon);
    setField(f, "location.timezone", c.location.timezone); setField(f, "units", c.units); setField(f, "clock_24h", c.clock_24h);
    $("panel-checks").innerHTML = Object.keys(PANEL_LABELS).map((k) => `<label class="check"><input type="checkbox" name="panels.${k}" ${c.panels[k] !== false ? "checked" : ""}> ${esc(PANEL_LABELS[k])}</label>`).join("");
    const w = forms.weather;
    setField(w, "weather.hourly_hours", c.weather.hourly_hours); setField(w, "weather.forecast_days", c.weather.forecast_days);
    setField(w, "weather.air_quality", c.weather.air_quality); setField(w, "weather.alerts", c.weather.alerts);
    setField(w, "weather.takeover", c.weather.takeover); setField(w, "weather.takeover_minutes", c.weather.takeover_minutes); setField(w, "weather.takeover_sound", c.weather.takeover_sound);
    const ca = forms.chronalert;
    for (const k of ["mode", "open_mode", "url", "show_seconds", "photo_seconds"]) setField(ca, "chronalert." + k, c.chronalert[k]);
    setField(w, "radar.zoom", c.radar.zoom); setField(w, "radar.provider", c.radar.provider);
    $("calendar-list").replaceChildren(...c.calendars.map((x) => row("cal", x)));
    setField(forms.calendars, "calendar.days_ahead", c.calendar.days_ahead); setField(forms.calendars, "calendar.max_events", c.calendar.max_events);
    $("stock-list").replaceChildren(...Object.entries(c.stocks.symbols).map(([sym, name]) => row("stock", { sym, name })));
    $("team-list").replaceChildren(...c.sports.teams.map((t) => row("team", t)));
    $("countdown-list").replaceChildren(...c.countdowns.map((x) => row("cd", x)));
    $("feed-list").replaceChildren(...c.news.feeds.map((x) => row("feed", x)));
    const p = forms.photos;
    setField(p, "photos.seconds_per_photo", c.photos.seconds_per_photo); setField(p, "photos.order", c.photos.order);
    setField(p, "photos.max_upload_mb", c.photos.max_upload_mb); setField(p, "todo.max_items", c.todo.max_items);
    const d = forms.display;
    for (const k of ["screen_off", "screen_on", "dim_from", "dim_level", "reload_at", "control", "start_at_login", "locked_kiosk", "stop_idle_lock"]) setField(d, "display." + k, c.display[k]);
    document.querySelectorAll("[data-secret]").forEach((el) => { const s = settings.secrets[el.dataset.secret]; el.textContent = s && s.set ? `currently: ${s.hint}` : "not set"; });
  }

  function collect(section, form) {
    const g = (n) => getField(form, n);
    switch (section) {
      case "location": return { config: { location: { name: g("location.name"), lat: Number(g("location.lat")), lon: Number(g("location.lon")), timezone: g("location.timezone") }, units: g("units"), clock_24h: g("clock_24h") } };
      case "panels": return { config: { panels: Object.fromEntries(Object.keys(PANEL_LABELS).map((k) => [k, g("panels." + k)])) } };
      case "weather": return { config: { weather: { hourly_hours: Number(g("weather.hourly_hours")), forecast_days: Number(g("weather.forecast_days")), air_quality: g("weather.air_quality"), alerts: g("weather.alerts"), takeover: g("weather.takeover"), takeover_minutes: Number(g("weather.takeover_minutes")), takeover_sound: g("weather.takeover_sound") }, radar: { zoom: Number(g("radar.zoom")), provider: g("radar.provider") } } };
      case "chronalert": return { config: { chronalert: { mode: g("chronalert.mode"), open_mode: g("chronalert.open_mode"), url: g("chronalert.url"), show_seconds: Number(g("chronalert.show_seconds")), photo_seconds: Number(g("chronalert.photo_seconds")) } } };
      case "calendars": return { config: { calendars: [...$("calendar-list").children].map((r) => ({ name: r.querySelector(".name").value, url: r.querySelector(".url").value, color: r.querySelector(".color").value })), calendar: { days_ahead: Number(g("calendar.days_ahead")), max_events: Number(g("calendar.max_events")) } } };
      case "stocks": return { config: { stocks: { symbols: Object.fromEntries([...$("stock-list").children].map((r) => [r.querySelector(".sym").value.trim().toUpperCase(), r.querySelector(".name").value.trim()]).filter(([s]) => s)) } } };
      case "sports": return { config: { sports: { teams: [...$("team-list").children].map((r) => JSON.parse(r.dataset.json)) } } };
      case "countdowns": return { config: { countdowns: [...$("countdown-list").children].map((r) => ({ title: r.querySelector(".title").value, date: r.querySelector(".date").value, icon: r.querySelector(".icon").value })) } };
      case "news": return { config: { news: { feeds: [...$("feed-list").children].map((r) => ({ name: r.querySelector(".name").value, url: r.querySelector(".url").value })) } } };
      case "photos": return { config: { photos: { seconds_per_photo: Number(g("photos.seconds_per_photo")), order: g("photos.order"), max_upload_mb: Number(g("photos.max_upload_mb")) }, todo: { max_items: Number(g("todo.max_items")) } } };
      case "display": return { config: { display: { screen_off: g("display.screen_off"), screen_on: g("display.screen_on"), dim_from: g("display.dim_from"), dim_level: g("display.dim_level"), reload_at: g("display.reload_at"), control: g("display.control"), start_at_login: g("display.start_at_login"), locked_kiosk: g("display.locked_kiosk"), stop_idle_lock: g("display.stop_idle_lock") } } };
      case "secrets": return { secrets: Object.fromEntries(["FINNHUB_API_KEY", "OUTLOOK_ICS_URL", "SPOTIFY_CLIENT_ID", "DASHBOARD_PIN"].map((k) => [k, g(k)])) };
    }
    return {};
  }
  document.querySelectorAll("form[data-section]").forEach((form) => form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = form.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      const body = collect(form.dataset.section, form);
      const r = await api("/api/settings", { method: "PUT", json: body });
      if (body.secrets && body.secrets.DASHBOARD_PIN) { pin = body.secrets.DASHBOARD_PIN.trim(); sessionStorage.setItem("dashboard_pin", pin); }
      toast(r.autostart ? `Saved. ${r.autostart}.` : "Saved. The dashboard updates by itself.");
      form.querySelectorAll('input[type=text][name]').forEach((el) => { if (form.dataset.section === "secrets") el.value = ""; });
      await loadSettings();
    } catch (err) { toast(err.message, true); }
    btn.disabled = false;
  }));
  $("clear-pin").addEventListener("click", async () => {
    if (!(await confirmAction("Remove the PIN? Anyone on your Wi-Fi can then change settings."))) return;
    try { await api("/api/settings", { method: "PUT", json: { secrets: { DASHBOARD_PIN: "__clear__" } } }); pin = ""; sessionStorage.removeItem("dashboard_pin"); toast("PIN removed"); loadSettings(); } catch (err) { toast(err.message, true); }
  });
  $("zip-lookup").addEventListener("click", async () => {
    const zip = $("zip").value.trim();
    try {
      const d = await api(`/api/zip/${encodeURIComponent(zip)}`);
      const f = document.querySelector('form[data-section="location"]');
      setField(f, "location.name", d.name); setField(f, "location.lat", d.lat); setField(f, "location.lon", d.lon); setField(f, "location.timezone", d.timezone);
      toast(`Found ${d.name}. Press Save.`);
    } catch (err) { toast(err.message, true); }
  });
  async function searchTeam() {
    const q = $("team-search").value.trim();
    if (q.length < 2) return;
    $("team-results").textContent = "Searching…";
    try {
      const d = await api(`/api/sports/search?q=${encodeURIComponent(q)}`);
      $("team-results").innerHTML = d.teams.length ? "" : "No teams found.";
      for (const t of d.teams) {
        const b = document.createElement("button"); b.type = "button";
        b.innerHTML = `${t.logo ? `<img src="${esc(t.logo)}" alt="">` : ""}<span>${esc(t.name)} <small class="hint">${esc(t.sport)} / ${esc(t.league)}</small></span>`;
        b.addEventListener("click", () => { $("team-list").replaceChildren(row("team", t)); $("team-results").innerHTML = ""; toast("Team picked. Press Save."); });
        $("team-results").appendChild(b);
      }
    } catch (err) { $("team-results").textContent = err.message; }
  }
  $("team-search-btn").addEventListener("click", searchTeam);
  $("team-search").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); searchTeam(); } });

  // ---------- music --------------------------------------------------------------------------
  async function loadMusic() {
    const d = await api("/api/spotify/status");
    $("music-redirect").textContent = d.redirect_uri;
    let status = d.connected ? "Connected to Spotify." : d.configured ? "Client ID saved. Not connected yet: follow step 4." : "Not set up yet: follow the steps below.";
    if (d.connected && d.now && d.now.data) status += d.now.data.playing ? ` Playing now: ${d.now.data.title} – ${d.now.data.artist}.` : " Nothing is playing right now.";
    if (d.connected && d.now && d.now.error) status += ` (${d.now.error})`;
    $("music-status").textContent = status;
    $("spotify-disconnect").classList.toggle("hidden", !d.connected);
  }
  $("spotify-connect").addEventListener("click", async () => {
    try {
      const d = await api("/api/spotify/login");
      if (KIOSK) location.href = d.url; else window.open(d.url, "_blank");
      toast("Approve in Spotify, then paste the address here.");
    } catch (err) { toast(err.message, true); }
  });
  $("spotify-paste-btn").addEventListener("click", async () => {
    try {
      await api("/api/spotify/paste", { method: "POST", json: { url: $("spotify-paste").value } });
      $("spotify-paste").value = "";
      toast("Spotify connected");
      loadMusic();
    } catch (err) { toast(err.message, true); }
  });
  $("spotify-disconnect").addEventListener("click", async () => {
    if (!(await confirmAction("Disconnect Spotify?"))) return;
    try { await api("/api/spotify/disconnect", { method: "POST" }); toast("Disconnected"); loadMusic(); } catch (err) { toast(err.message, true); }
  });

  // ---------- system -------------------------------------------------------------------------
  function fmtUptime(s) { const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return h ? `${h} h ${m} min` : `${m} min`; }
  async function loadSystem() {
    const d = await api("/api/system");
    let win = "unknown";
    try { const disp = await api("/api/display"); win = disp.dashboard_window === "running" ? "showing on the Pi's screen" : "closed (the Pi is showing its desktop)"; } catch (e) { /* ignore */ }
    const rows = [
      ["Computer", `${d.machine} · ${d.platform}`],
      ["Dashboard window", win],
      ["Dashboard address", `http://${d.hostname}.local:${d.port}  (${d.ip ? "http://" + d.ip + ":" + d.port : "IP unknown"})`],
      ["Version", d.version], ["Running for", fmtUptime(d.uptime_seconds)], ["Free disk", `${d.disk_free_gb} GB`],
      ["Pi temperature", d.cpu_temp_c != null ? `${d.cpu_temp_c} °C` : "n/a"],
      ["Keys set", Object.entries(d.secrets_set).filter(([, v]) => v).map(([k]) => k).join(", ") || "none"],
      ["Still needed", d.setup_needed.join(", ") || "nothing, all set"],
      ["iPhone HEIC photos", d.heic_supported ? "supported" : "not supported"],
      ["Mode", d.mock ? "sample data (DASHBOARD_MOCK=1)" : "live"],
    ];
    $("system-info").innerHTML = rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
  }
  const ACTIONS = {
    restart: { path: "/api/system/restart", confirm: "Restart the dashboard? The screen goes blank for about 10 seconds." },
    update: { path: "/api/system/update", confirm: "Download the latest version and restart?" },
    reboot: { path: "/api/system/reboot", confirm: "Reboot the Pi? It takes about a minute." },
    "screen-off": { path: "/api/display/off" }, "screen-on": { path: "/api/display/on" },
    desktop: { path: "/api/display/desktop", confirm: "Close the dashboard window on the Pi and show its desktop?" },
    dashboard: { path: "/api/display/dashboard" },
  };
  document.querySelectorAll("[data-action]").forEach((btn) => btn.addEventListener("click", async () => {
    const a = ACTIONS[btn.dataset.action];
    if (a.confirm && !(await confirmAction(a.confirm))) return;
    btn.disabled = true;
    const log = $("action-log");
    try {
      const d = await api(a.path, { method: "POST" });
      toast(d.message || "Done");
      if (d.log) { log.textContent = d.log; log.classList.remove("hidden"); }
      if (btn.dataset.action === "desktop" || btn.dataset.action === "dashboard") setTimeout(loadSystem, 2500);
    } catch (err) { toast(err.message, true); }
    btn.disabled = false;
  }));

  // ---------- on-screen keyboard (TV / touch) -------------------------------------------------
  const KEYS = [["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"], ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"], ["a", "s", "d", "f", "g", "h", "j", "k", "l", ":"], ["⇧", "z", "x", "c", "v", "b", "n", "m", ".", "-"], ["/", "@", "_", "#", "space", "⌫", "Done"]];
  let kbdTarget = null, shift = false;
  function buildKeyboard() {
    const box = $("kbd");
    box.innerHTML = KEYS.map((r) => `<div class="krow">${r.map((k) => `<button type="button" data-k="${esc(k)}" class="${k === "space" ? "space" : k === "Done" ? "wide go" : k === "⌫" || k === "⇧" ? "wide" : ""}">${k === "space" ? "" : esc(k)}</button>`).join("")}</div>`).join("");
    box.addEventListener("mousedown", (e) => e.preventDefault());  // keep focus in the field
    box.addEventListener("click", (e) => {
      const k = e.target.dataset && e.target.dataset.k;
      if (!k || !kbdTarget) return;
      if (k === "Done") { box.classList.add("hidden"); document.body.classList.remove("kiosk-kbd"); kbdTarget.blur(); return; }
      if (k === "⇧") { shift = !shift; box.querySelectorAll("button").forEach((b) => { const v = b.dataset.k; if (v.length === 1 && /[a-z]/i.test(v)) b.textContent = shift ? v.toUpperCase() : v.toLowerCase(); }); return; }
      const t = kbdTarget, start = t.selectionStart ?? t.value.length, end = t.selectionEnd ?? t.value.length;
      let v = t.value;
      if (k === "⌫") { v = v.slice(0, Math.max(0, start - (start === end ? 1 : 0))) + v.slice(end); t.value = v; const pos = Math.max(0, start - (start === end ? 1 : 0)); try { t.setSelectionRange(pos, pos); } catch (x) {} }
      else { const ch = k === "space" ? " " : shift ? k.toUpperCase() : k; t.value = v.slice(0, start) + ch + v.slice(end); try { t.setSelectionRange(start + ch.length, start + ch.length); } catch (x) {} }
      t.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }
  function enableKeyboard() {
    buildKeyboard();
    $("kbd-toggle").classList.remove("hidden");
    let on = true;
    $("kbd-toggle").addEventListener("click", () => { on = !on; if (!on) { $("kbd").classList.add("hidden"); document.body.classList.remove("kiosk-kbd"); } toast(on ? "On-screen keyboard on" : "On-screen keyboard off"); });
    document.addEventListener("focusin", (e) => {
      const t = e.target;
      if (!on || !(t.matches("input[type=text], input[type=password], input[type=number], textarea, input:not([type])"))) return;
      kbdTarget = t;
      $("kbd").classList.remove("hidden");
      document.body.classList.add("kiosk-kbd");
      setTimeout(() => t.scrollIntoView({ block: "center", behavior: "smooth" }), 50);
    });
  }

  // ---------- boot ---------------------------------------------------------------------------
  async function boot() {
    if (KIOSK) { document.body.classList.add("kiosk"); $("back").classList.remove("hidden"); enableKeyboard(); }
    try { config = await fetch("/api/config", { cache: "no-store" }).then((r) => r.json()); } catch (e) { config = {}; }
    if (config.pin_required && !pin) { showPinGate(); return; }
    showTab(location.hash.slice(1) || "photos");
  }
  boot();
})();
