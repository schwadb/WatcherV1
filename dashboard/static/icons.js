/* Inline SVG weather and moon icons, keyed by the names the server sends. */
(function () {
  const wrap = (body) =>
    `<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;

  const sun = '<circle cx="32" cy="32" r="11"/><path d="M32 8v6M32 50v6M8 32h6M50 32h6M15 15l4 4M45 45l4 4M15 49l4-4M45 19l4-4"/>';
  const moon = '<path d="M40 10a20 20 0 1 0 14 34 16 16 0 0 1-14-34z"/>';
  const cloud = '<path d="M20 48h26a10 10 0 0 0 1-20 14 14 0 0 0-27 4 8 8 0 0 0 0 16z"/>';
  const cloudSmall = '<path d="M24 52h24a8 8 0 0 0 1-16 11 11 0 0 0-21 3 6.5 6.5 0 0 0-4 13z"/>';
  const rainDrops = '<path d="M24 54l-3 6M34 54l-3 6M44 54l-3 6"/>';
  const drizzleDots = '<path d="M25 55v1M35 55v1M45 55v1"/>';
  const snowDots = '<path d="M25 56h.1M35 56h.1M45 56h.1" stroke-width="5"/>';
  const bolt = '<path d="M35 46l-6 10h6l-4 8" stroke="#f5b942"/>';

  const icons = {
    clear: wrap(sun),
    "clear-night": wrap(moon),
    "partly-cloudy": wrap('<circle cx="22" cy="22" r="8"/><path d="M22 6v4M22 34v4M6 22h4M34 22h4M11 11l3 3M30 30l3 3M11 33l3-3M30 14l3-3"/>' + cloudSmall),
    "partly-cloudy-night": wrap('<path d="M22 8a11 11 0 1 0 9 18 9 9 0 0 1-9-18z"/>' + cloudSmall),
    cloudy: wrap(cloud),
    fog: wrap('<path d="M14 26h36M10 36h44M16 46h32"/>'),
    drizzle: wrap(cloud.replace("48", "44") + drizzleDots),
    rain: wrap(cloud.replace("48", "44") + rainDrops),
    showers: wrap(cloud.replace("48", "44") + rainDrops),
    sleet: wrap(cloud.replace("48", "44") + '<path d="M24 54l-3 6M44 54l-3 6"/><path d="M34 57h.1" stroke-width="5"/>'),
    snow: wrap(cloud.replace("48", "44") + snowDots),
    thunder: wrap(cloud.replace("48", "44") + bolt),
  };

  window.weatherIcon = function (name, isDay) {
    if (isDay === false && icons[name + "-night"]) return icons[name + "-night"];
    return icons[name] || icons.cloudy;
  };

  /** Moon disc for a phase 0..1 (0 = new, 0.5 = full). Lit part in currentColor, dark part dim. */
  window.moonIcon = function (phase) {
    const r = 22, cx = 32, top = cx - r, bottom = cx + r;
    const p = ((Number(phase) || 0) % 1 + 1) % 1;
    const rx = Math.abs(Math.cos(2 * Math.PI * p)) * r;
    let lit = "";
    if (p < 0.02 || p > 0.98) lit = "";                              // new moon
    else if (Math.abs(p - 0.5) < 0.02) lit = `<circle cx="${cx}" cy="${cx}" r="${r}" fill="currentColor" stroke="none"/>`;
    else {
      const waxing = p < 0.5;
      const crescent = waxing ? p < 0.25 : p > 0.75;
      // outer edge on the lit side, then back along the terminator ellipse
      const outerSweep = waxing ? 1 : 0;
      const backSweep = waxing ? (crescent ? 0 : 1) : (crescent ? 1 : 0);
      lit = `<path d="M${cx} ${top} A${r} ${r} 0 0 ${outerSweep} ${cx} ${bottom} A${rx.toFixed(2)} ${r} 0 0 ${backSweep} ${cx} ${top}Z" fill="currentColor" stroke="none"/>`;
    }
    return `<svg viewBox="0 0 64 64" aria-hidden="true"><circle cx="${cx}" cy="${cx}" r="${r}" fill="rgba(255,255,255,0.12)"/>${lit}</svg>`;
  };
})();
