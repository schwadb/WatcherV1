// Application state + UI. No framework: explicit render functions per panel.
import maplibregl from 'maplibre-gl';
import Papa from 'papaparse';
import type { Boundaries } from './boundaries';
import { downloadText, exportMap } from './exporter';
import { geocodeOne, guessColumns, parseCsv, parseLatLng, rowAddress, type ParsedCsv } from './importer';
import type { TmMap } from './map';
import { DETAIL_LEVELS, downloadArea, estimateArea, fmtBytes, removeArea } from './offline';
import { listAreas, listProjects, deleteProject as removeProject, requestPersistence, saveProject, storageEstimate } from './storage';
import {
  assignUnit, assignmentsToCsv, computeStats, importAssignments, newTerritoryName, nextColor, PALETTE, removeTerritory,
} from './territories';
import type { PinLayer, Project, UnitLevel } from './types';

const $ = <T extends HTMLElement = HTMLElement>(sel: string): T => document.querySelector(sel) as T;
const el = (html: string): HTMLElement => {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild as HTMLElement;
};
const uid = () => crypto.randomUUID();

export class App {
  project!: Project;
  boundaries!: Boundaries;
  tm!: TmMap;
  activeTerritoryId: string | null = null;
  eraseMode = false;
  private saveTimer: number | undefined;
  private downloadAbort: AbortController | null = null;

  async init(project: Project, boundaries: Boundaries, tm: TmMap): Promise<void> {
    this.project = project;
    this.boundaries = boundaries;
    this.tm = tm;
    this.activeTerritoryId = project.territories[0]?.id ?? null;

    tm.setUnitLevel(project.unitLevel);
    this.applyAssignmentColors();
    this.rebuildPins();
    this.wireChrome();
    this.wirePainting();
    this.wirePins();
    this.renderAll();

    window.addEventListener('online', () => this.updateNetStatus());
    window.addEventListener('offline', () => this.updateNetStatus());
    this.updateNetStatus();
    requestPersistence();

    tm.map.on('moveend', () => {
      const c = tm.map.getCenter();
      this.project.mapView = { center: [c.lng, c.lat], zoom: tm.map.getZoom() };
      this.scheduleSave();
      if ($('#panel-offline').classList.contains('active')) this.renderOfflinePanel();
    });
  }

  // ---------- persistence ----------

  scheduleSave(): void {
    $('#save-dot').classList.add('dirty');
    clearTimeout(this.saveTimer);
    this.saveTimer = window.setTimeout(async () => {
      this.project.updatedAt = new Date().toISOString();
      await saveProject(this.project);
      $('#save-dot').classList.remove('dirty');
    }, 700);
  }

  // ---------- map coloring ----------

  applyAssignmentColors(): void {
    this.tm.clearUnitColors();
    const colors = new Map(this.project.territories.map((t) => [t.id, t.color]));
    for (const [fips, tid] of Object.entries(this.project.assignments)) {
      const c = colors.get(tid);
      if (c) this.tm.setUnitColor(parseInt(fips, 10), c);
    }
  }

  rebuildPins(): void {
    const features: GeoJSON.Feature[] = [];
    for (const layer of this.project.pinLayers) {
      if (!layer.visible) continue;
      const catColors = this.categoryColors(layer);
      for (const pin of layer.pins) {
        const cat = layer.colorBy ? (pin.props[layer.colorBy] ?? '') : '';
        features.push({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [pin.lng, pin.lat] },
          properties: { ...pin.props, _color: catColors.get(cat) ?? '#e15759', _layer: layer.name },
        });
      }
    }
    const data: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features };
    const src = this.tm.map.getSource('pins') as maplibregl.GeoJSONSource | undefined;
    if (src) src.setData(data);
    else {
      this.tm.map.addSource('pins', { type: 'geojson', data });
      this.tm.map.addLayer({
        id: 'pins',
        type: 'circle',
        source: 'pins',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 3, 10, 6.5],
          'circle-color': ['get', '_color'],
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 1.2,
        },
      });
    }
  }

  categoryColors(layer: PinLayer): Map<string, string> {
    const m = new Map<string, string>();
    if (!layer.colorBy) return m;
    const values = [...new Set(layer.pins.map((p) => p.props[layer.colorBy!] ?? ''))].sort();
    values.forEach((v, i) => m.set(v, PALETTE[i % PALETTE.length]));
    return m;
  }

  // ---------- chrome ----------

  private wireChrome(): void {
    const nameInput = $('#project-name') as HTMLInputElement;
    nameInput.value = this.project.name;
    nameInput.addEventListener('input', () => {
      this.project.name = nameInput.value;
      this.scheduleSave();
    });
    $('#btn-export').addEventListener('click', () => this.openExportModal());
    document.querySelectorAll<HTMLButtonElement>('#tabs .tab').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#tabs .tab').forEach((b) => b.classList.remove('active'));
        document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
        btn.classList.add('active');
        $(`#panel-${btn.dataset.tab}`).classList.add('active');
        if (btn.dataset.tab === 'offline') this.renderOfflinePanel();
      });
    });
  }

  private updateNetStatus(): void {
    $('#net-status').hidden = navigator.onLine;
  }

  toast(msg: string, ms = 3200): void {
    const t = $('#toast');
    t.textContent = msg;
    t.hidden = false;
    clearTimeout((t as unknown as { _timer?: number })._timer);
    (t as unknown as { _timer?: number })._timer = window.setTimeout(() => (t.hidden = true), ms);
  }

  renderAll(): void {
    this.renderTerritoriesPanel();
    this.renderDataPanel();
    this.renderProjectPanel();
    this.renderLegend();
  }

  // ---------- painting ----------

  private wirePainting(): void {
    const map = this.tm.map;
    let painting = false;
    let lastFips: string | null = null;

    const unitAt = (point: maplibregl.Point): string | null => {
      const layer = `${this.project.unitLevel}-fill`;
      if (!map.getLayer(layer)) return null;
      const feats = map.queryRenderedFeatures(point, { layers: [layer] });
      const f = feats[0];
      return f ? ((f.properties as { fips?: string }).fips ?? null) : null;
    };

    const paint = (fips: string, erase: boolean) => {
      if (fips === lastFips && painting) return;
      lastFips = fips;
      const tid = erase ? null : this.activeTerritoryId;
      if (!erase && !tid) {
        this.toast('Add a territory first (Territories panel)');
        return;
      }
      if (assignUnit(this.project, fips, tid)) {
        const color = tid ? this.project.territories.find((t) => t.id === tid)?.color ?? null : null;
        this.tm.setUnitColor(parseInt(fips, 10), color);
        this.scheduleSave();
        this.refreshStatsSoon();
      }
    };

    map.on('mousedown', (e) => {
      if (e.originalEvent.button !== 0) return;
      const fips = unitAt(e.point);
      if (!fips) return;
      painting = true;
      lastFips = null;
      map.dragPan.disable();
      paint(fips, this.eraseMode || e.originalEvent.altKey);
    });
    map.on('mousemove', (e) => {
      const fips = unitAt(e.point);
      // hover outline
      const hoverLayer = `${this.project.unitLevel}-hover`;
      if (map.getLayer(hoverLayer)) {
        map.setFilter(hoverLayer, ['==', ['id'], fips ? parseInt(fips, 10) : -1]);
      }
      map.getCanvas().style.cursor = fips ? 'crosshair' : '';
      if (painting && fips) paint(fips, this.eraseMode || e.originalEvent.altKey);
    });
    const stop = () => {
      painting = false;
      lastFips = null;
      map.dragPan.enable();
    };
    map.on('mouseup', stop);
    map.getCanvas().addEventListener('mouseleave', stop);
    // touch: tap assigns
    map.on('click', (e) => {
      if ((e.originalEvent as PointerEvent).pointerType === 'touch') {
        const fips = unitAt(e.point);
        if (fips) paint(fips, this.eraseMode);
      }
    });
  }

  private statsTimer: number | undefined;
  refreshStatsSoon(): void {
    clearTimeout(this.statsTimer);
    this.statsTimer = window.setTimeout(() => {
      this.renderTerritoriesPanel();
      this.renderLegend();
    }, 120);
  }

  // ---------- pins interactions ----------

  private wirePins(): void {
    const map = this.tm.map;
    map.on('click', 'pins', (e) => {
      const f = e.features?.[0];
      if (!f) return;
      const props = { ...(f.properties as Record<string, string>) };
      const layerName = props._layer;
      delete props._color;
      delete props._layer;
      const rows = Object.entries(props)
        .slice(0, 10)
        .map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(String(v))}</td></tr>`)
        .join('');
      new maplibregl.Popup({ closeButton: true, maxWidth: '320px' })
        .setLngLat((f.geometry as GeoJSON.Point).coordinates as [number, number])
        .setHTML(`<strong>${esc(layerName)}</strong><table class="popup-table">${rows}</table>`)
        .addTo(map);
    });
    map.on('mouseenter', 'pins', () => (map.getCanvas().style.cursor = 'pointer'));
    map.on('mouseleave', 'pins', () => (map.getCanvas().style.cursor = ''));
  }

  // ---------- territories panel ----------

  renderTerritoriesPanel(): void {
    const stats = computeStats(this.project, this.boundaries);
    const p = $('#panel-territories');
    p.innerHTML = '';
    p.append(el(`<h3>Territories</h3>`));
    p.append(
      el(
        `<p class="hint">Paint <b>${this.project.unitLevel === 'county' ? 'counties' : 'states'}</b> on the map: click or click-drag to assign to the selected territory. Alt-click (or Erase mode) removes.</p>`,
      ),
    );

    const levelRow = el(`<div class="row"><label>Building blocks</label></div>`);
    const levelSel = el(
      `<select><option value="county">Counties</option><option value="state">States</option></select>`,
    ) as HTMLSelectElement;
    levelSel.value = this.project.unitLevel;
    levelSel.addEventListener('change', () => {
      this.project.unitLevel = levelSel.value as UnitLevel;
      this.tm.setUnitLevel(this.project.unitLevel);
      this.applyAssignmentColors();
      this.scheduleSave();
      this.renderTerritoriesPanel();
      this.renderLegend();
    });
    levelRow.append(levelSel);
    p.append(levelRow);

    const list = el(`<div></div>`);
    for (const t of this.project.territories) {
      const s = stats.get(t.id);
      const item = el(`<div class="terr-item ${t.id === this.activeTerritoryId ? 'active' : ''}"></div>`);
      const swatch = el(`<input type="color" class="terr-swatch" value="${t.color}" title="Territory color" />`) as HTMLInputElement;
      swatch.addEventListener('input', () => {
        t.color = swatch.value;
        this.applyAssignmentColors();
        this.scheduleSave();
        this.renderLegend();
      });
      const name = el(`<input class="terr-name" value="${escAttr(t.name)}" />`) as HTMLInputElement;
      name.addEventListener('input', () => {
        t.name = name.value;
        this.scheduleSave();
        this.renderLegend();
      });
      name.addEventListener('click', (e) => e.stopPropagation());
      const valueSum = s ? Object.values(s.valueSums).reduce((a, b) => a + b, 0) : 0;
      const statText = s
        ? `${s.unitCount} ${this.project.unitLevel === 'county' ? 'cty' : 'st'} · pop ${fmtNum(s.population)}${s.pinCount ? ` · ${s.pinCount} pins` : ''}${valueSum ? ` · ${fmtNum(valueSum)}` : ''}`
        : '';
      const stat = el(`<span class="terr-stats">${statText}</span>`);
      const x = el(`<button class="terr-x" title="Delete territory">✕</button>`);
      x.addEventListener('click', (e) => {
        e.stopPropagation();
        removeTerritory(this.project, t.id);
        if (this.activeTerritoryId === t.id) this.activeTerritoryId = this.project.territories[0]?.id ?? null;
        this.applyAssignmentColors();
        this.scheduleSave();
        this.renderTerritoriesPanel();
        this.renderLegend();
      });
      item.append(swatch, name, stat, x);
      item.addEventListener('click', () => {
        this.activeTerritoryId = t.id;
        this.eraseMode = false;
        this.renderTerritoriesPanel();
      });
      list.append(item);
    }
    p.append(list);

    const addBtn = el(`<button class="btn">+ Add territory</button>`);
    addBtn.addEventListener('click', () => {
      const t = { id: uid(), name: newTerritoryName(this.project), color: nextColor(this.project) };
      this.project.territories.push(t);
      this.activeTerritoryId = t.id;
      this.eraseMode = false;
      this.scheduleSave();
      this.renderTerritoriesPanel();
      this.renderLegend();
    });
    const eraseBtn = el(`<button class="btn ${this.eraseMode ? 'primary' : ''}">Erase mode</button>`);
    eraseBtn.addEventListener('click', () => {
      this.eraseMode = !this.eraseMode;
      this.renderTerritoriesPanel();
    });
    const btnRow = el(`<div class="row"></div>`);
    btnRow.append(addBtn, eraseBtn);
    p.append(btnRow);

    const io = el(`<section><h3>Assignments</h3></section>`);
    const exportBtn = el(`<button class="btn small">Export CSV</button>`);
    exportBtn.addEventListener('click', () => {
      downloadText(assignmentsToCsv(this.project, this.boundaries), `${this.project.name}-territories.csv`, 'text/csv');
    });
    const importBtn = el(`<button class="btn small">Import CSV</button>`);
    importBtn.addEventListener('click', () => this.openAssignmentImport());
    const clearBtn = el(`<button class="btn small danger">Clear all</button>`);
    clearBtn.addEventListener('click', () => {
      if (!confirm('Remove all territory assignments?')) return;
      this.project.assignments = {};
      this.applyAssignmentColors();
      this.scheduleSave();
      this.renderTerritoriesPanel();
      this.renderLegend();
    });
    const ioRow = el(`<div class="row"></div>`);
    ioRow.append(exportBtn, importBtn, clearBtn);
    io.append(el(`<p class="hint">The FIPS→Territory spreadsheet is the standard interchange format — reimport it later or hand it to other tools.</p>`), ioRow);
    p.append(io);
  }

  private openAssignmentImport(): void {
    this.showModal(
      `<h3>Import territory assignments</h3>
       <p class="hint">CSV with a FIPS column and a Territory column (header row required). Territories are created by name as needed.</p>
       <textarea id="assign-csv" placeholder="CountyFIPS,Territory\n06075,West Coast\n06081,West Coast"></textarea>
       <div class="row"><input type="file" id="assign-file" accept=".csv,text/csv" /></div>
       <div class="modal-actions"><button class="btn" data-close>Cancel</button><button class="btn primary" id="assign-go">Import</button></div>`,
    );
    const fileInput = $('#assign-file') as HTMLInputElement;
    fileInput.addEventListener('change', async () => {
      const f = fileInput.files?.[0];
      if (f) ($('#assign-csv') as HTMLTextAreaElement).value = await f.text();
    });
    $('#assign-go').addEventListener('click', () => {
      const text = ($('#assign-csv') as HTMLTextAreaElement).value;
      const parsed = Papa.parse<Record<string, string>>(text.trim(), { header: true, skipEmptyLines: true });
      const n = importAssignments(this.project, parsed.data, uid);
      this.applyAssignmentColors();
      this.scheduleSave();
      this.renderTerritoriesPanel();
      this.renderLegend();
      this.closeModal();
      this.toast(`Imported ${n} assignments`);
    });
  }

  // ---------- data panel ----------

  renderDataPanel(): void {
    const p = $('#panel-data');
    p.innerHTML = '';
    p.append(el(`<h3>Pin data</h3>`));
    p.append(el(`<p class="hint">Import a spreadsheet of locations — paste from Excel or choose a CSV. Rows with lat/long map instantly; addresses are geocoded free via the US Census Bureau.</p>`));

    for (const layer of this.project.pinLayers) {
      const item = el(`<div class="layer-item"></div>`);
      const head = el(`<div class="layer-head"></div>`);
      const vis = el(`<input type="checkbox" ${layer.visible ? 'checked' : ''} title="Show layer" />`) as HTMLInputElement;
      vis.addEventListener('change', () => {
        layer.visible = vis.checked;
        this.rebuildPins();
        this.scheduleSave();
        this.renderLegend();
        this.refreshStatsSoon();
      });
      const name = el(`<span class="name">${esc(layer.name)}</span>`);
      const count = el(`<span class="terr-stats">${layer.pins.length} pins</span>`);
      const zoom = el(`<button class="btn small" title="Zoom to layer">⌖</button>`);
      zoom.addEventListener('click', () => this.zoomToLayer(layer));
      const x = el(`<button class="terr-x" title="Delete layer">✕</button>`);
      x.addEventListener('click', () => {
        if (!confirm(`Delete layer "${layer.name}"?`)) return;
        this.project.pinLayers = this.project.pinLayers.filter((l) => l.id !== layer.id);
        this.rebuildPins();
        this.scheduleSave();
        this.renderDataPanel();
        this.renderLegend();
        this.refreshStatsSoon();
      });
      head.append(vis, name, count, zoom, x);
      item.append(head);

      const columns = layer.pins[0] ? Object.keys(layer.pins[0].props) : [];
      const colorRow = el(`<div class="row"><label>Color by</label></div>`);
      const colorSel = el(
        `<select><option value="">— single color —</option>${columns.map((c) => `<option ${layer.colorBy === c ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select>`,
      ) as HTMLSelectElement;
      colorSel.addEventListener('change', () => {
        layer.colorBy = colorSel.value || null;
        this.rebuildPins();
        this.scheduleSave();
        this.renderLegend();
      });
      colorRow.append(colorSel);
      const valRow = el(`<div class="row"><label>Sum column</label></div>`);
      const valSel = el(
        `<select><option value="">— none —</option>${columns.map((c) => `<option ${layer.valueColumn === c ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select>`,
      ) as HTMLSelectElement;
      valSel.addEventListener('change', () => {
        layer.valueColumn = valSel.value || null;
        this.scheduleSave();
        this.refreshStatsSoon();
      });
      valRow.append(valSel);
      item.append(colorRow, valRow);
      p.append(item);
    }

    const importBtn = el(`<button class="btn primary">+ Import spreadsheet</button>`);
    importBtn.addEventListener('click', () => this.openCsvImport());
    p.append(importBtn);
  }

  private zoomToLayer(layer: PinLayer): void {
    if (!layer.pins.length) return;
    const b = new maplibregl.LngLatBounds();
    for (const pin of layer.pins) b.extend([pin.lng, pin.lat]);
    this.tm.map.fitBounds(b, { padding: 60, maxZoom: 11 });
  }

  private openCsvImport(): void {
    this.showModal(
      `<h3>Import spreadsheet</h3>
       <textarea id="csv-text" placeholder="Paste CSV here (with a header row)…"></textarea>
       <div class="row"><input type="file" id="csv-file" accept=".csv,.txt,text/csv" /></div>
       <div id="csv-mapping"></div>
       <div class="modal-actions"><button class="btn" data-close>Cancel</button><button class="btn primary" id="csv-next">Next</button></div>`,
    );
    const textEl = $('#csv-text') as HTMLTextAreaElement;
    const fileInput = $('#csv-file') as HTMLInputElement;
    fileInput.addEventListener('change', async () => {
      const f = fileInput.files?.[0];
      if (f) textEl.value = await f.text();
    });
    $('#csv-next').addEventListener('click', () => {
      const parsed = parseCsv(textEl.value);
      if (!parsed.columns.length || !parsed.rows.length) {
        this.toast('Nothing to import — paste CSV with a header row');
        return;
      }
      this.showColumnMapping(parsed);
    });
  }

  private showColumnMapping(parsed: ParsedCsv): void {
    const g = guessColumns(parsed.columns);
    const opts = (sel: string | null) =>
      `<option value="">—</option>` +
      parsed.columns.map((c) => `<option ${c === sel ? 'selected' : ''}>${esc(c)}</option>`).join('');
    this.showModal(
      `<h3>Map columns <span style="font-weight:400;color:var(--muted)">(${parsed.rows.length} rows)</span></h3>
       <div class="row"><label>Layer name</label><input type="text" id="m-layer" value="Imported ${this.project.pinLayers.length + 1}" /></div>
       <table class="map-table">
         <tr><td>Latitude</td><td><select id="m-lat">${opts(g.lat)}</select></td></tr>
         <tr><td>Longitude</td><td><select id="m-lng">${opts(g.lng)}</select></td></tr>
         <tr><td colspan="2" class="hint" style="padding-top:8px">…or geocode from address columns:</td></tr>
         <tr><td>Street address</td><td><select id="m-addr">${opts(g.address)}</select></td></tr>
         <tr><td>City</td><td><select id="m-city">${opts(g.city)}</select></td></tr>
         <tr><td>State</td><td><select id="m-state">${opts(g.state)}</select></td></tr>
         <tr><td>ZIP</td><td><select id="m-zip">${opts(g.zip)}</select></td></tr>
       </table>
       <div id="import-progress"></div>
       <div class="modal-actions"><button class="btn" data-close>Cancel</button><button class="btn primary" id="m-go">Import</button></div>`,
    );
    $('#m-go').addEventListener('click', () => this.runImport(parsed));
  }

  private async runImport(parsed: ParsedCsv): Promise<void> {
    const val = (id: string) => ($(id) as HTMLSelectElement).value || null;
    const mapping = {
      lat: val('#m-lat'), lng: val('#m-lng'), address: val('#m-addr'),
      city: val('#m-city'), state: val('#m-state'), zip: val('#m-zip'), name: null,
    };
    const layerName = ($('#m-layer') as HTMLInputElement).value || 'Imported';
    const goBtn = $('#m-go') as HTMLButtonElement;
    goBtn.disabled = true;
    const progress = $('#import-progress');

    const layer: PinLayer = { id: uid(), name: layerName, visible: true, colorBy: null, valueColumn: null, pins: [] };
    let geocoded = 0, failed = 0, direct = 0;
    const needGeocode = !mapping.lat || !mapping.lng;

    for (let i = 0; i < parsed.rows.length; i++) {
      const row = parsed.rows[i];
      let lat: number | null = null, lng: number | null = null;
      let source: 'coords' | 'census' = 'coords';
      const ll = parseLatLng(row, mapping);
      if (ll) {
        lat = ll.lat; lng = ll.lng; direct++;
      } else if (needGeocode || mapping.address || mapping.zip) {
        const addr = rowAddress(row, mapping);
        if (addr) {
          progress.innerHTML = `<div class="progress"><div style="width:${Math.round((i / parsed.rows.length) * 100)}%"></div></div><p class="hint">Geocoding ${i + 1} / ${parsed.rows.length}…</p>`;
          const r = await geocodeOne(addr);
          if (r) { lat = r.lat; lng = r.lng; source = 'census'; geocoded++; }
          await new Promise((res) => setTimeout(res, 120)); // be polite to the free service
        }
      }
      if (lat === null || lng === null) { failed++; continue; }
      layer.pins.push({
        id: uid(), lat, lng, props: row, source,
        countyFips: this.boundaries.countyOf([lng, lat]),
      });
    }

    if (!layer.pins.length) {
      progress.innerHTML = `<p class="hint">No rows could be placed. Check the column mapping.</p>`;
      goBtn.disabled = false;
      return;
    }
    this.project.pinLayers.push(layer);
    this.rebuildPins();
    this.scheduleSave();
    this.closeModal();
    this.renderDataPanel();
    this.renderLegend();
    this.refreshStatsSoon();
    this.zoomToLayer(layer);
    this.toast(
      `Imported ${layer.pins.length} pins (${direct} with coordinates, ${geocoded} geocoded${failed ? `, ${failed} failed` : ''})`,
      5000,
    );
  }

  // ---------- offline panel ----------

  async renderOfflinePanel(): Promise<void> {
    const p = $('#panel-offline');
    p.innerHTML = '';
    p.append(el(`<h3>Offline maps</h3>`));
    p.append(el(`<p class="hint">Download the map area you're looking at, then everything here — pins, territories, exports — keeps working with no internet.</p>`));

    const est = await storageEstimate();
    if (est) {
      p.append(el(`<p class="hint">Storage used: <b>${fmtBytes(est.usage)}</b> of ~${fmtBytes(est.quota)} available.</p>`));
    }

    const nameRow = el(`<div class="row"><label>Area name</label></div>`);
    const areas = await listAreas();
    const nameInput = el(`<input type="text" id="area-name" value="Area ${areas.length + 1}" />`) as HTMLInputElement;
    nameRow.append(nameInput);
    const detailRow = el(`<div class="row"><label>Detail</label></div>`);
    const detailSel = el(
      `<select id="area-detail">${DETAIL_LEVELS.map((d, i) => `<option value="${d.maxZoom}" ${i === 1 ? 'selected' : ''}>${d.label}</option>`).join('')}</select>`,
    ) as HTMLSelectElement;
    detailRow.append(detailSel);
    p.append(nameRow, detailRow);

    const estimate = el(`<p class="hint"></p>`);
    const updateEstimate = () => {
      const b = this.tm.map.getBounds();
      const bbox: [number, number, number, number] = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
      const e = estimateArea(bbox, parseInt(detailSel.value, 10));
      estimate.innerHTML = `Current view ≈ <b>${e.tiles.toLocaleString()} tiles, ~${fmtBytes(e.bytes)}</b>${e.bytes > 250_000_000 ? ' — zoom in or pick lower detail' : ''}`;
    };
    updateEstimate();
    detailSel.addEventListener('change', updateEstimate);
    p.append(estimate);

    const dlBtn = el(`<button class="btn primary">Download current view</button>`) as HTMLButtonElement;
    const cancelBtn = el(`<button class="btn" hidden>Cancel</button>`) as HTMLButtonElement;
    const prog = el(`<div></div>`);
    dlBtn.addEventListener('click', async () => {
      const b = this.tm.map.getBounds();
      const bbox: [number, number, number, number] = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
      const maxZoom = parseInt(detailSel.value, 10);
      const est2 = estimateArea(bbox, maxZoom);
      if (est2.bytes > 250_000_000 && !confirm(`This looks large (~${fmtBytes(est2.bytes)}). Download anyway?`)) return;
      dlBtn.disabled = true;
      cancelBtn.hidden = false;
      this.downloadAbort = new AbortController();
      try {
        const area = await downloadArea(
          nameInput.value || 'Area',
          bbox,
          maxZoom,
          this.tm.tileTemplate,
          (pr) => {
            prog.innerHTML = `<div class="progress"><div style="width:${Math.round((pr.done / pr.total) * 100)}%"></div></div><p class="hint">${pr.done.toLocaleString()} / ${pr.total.toLocaleString()} tiles · ${fmtBytes(pr.bytes)}${pr.failed ? ` · ${pr.failed} failed` : ''}</p>`;
          },
          this.downloadAbort.signal,
        );
        this.toast(`Saved "${area.name}" for offline use (${fmtBytes(area.sizeBytes)})`);
        this.renderOfflinePanel();
      } catch (err) {
        if ((err as Error).name === 'AbortError') this.toast('Download cancelled');
        else {
          console.error(err);
          this.toast('Download failed — check your connection');
        }
        dlBtn.disabled = false;
        cancelBtn.hidden = true;
        prog.innerHTML = '';
      }
    });
    cancelBtn.addEventListener('click', () => this.downloadAbort?.abort());
    const dlRow = el(`<div class="row"></div>`);
    dlRow.append(dlBtn, cancelBtn);
    p.append(dlRow, prog);

    if (areas.length) {
      const sec = el(`<section><h3>Saved areas</h3></section>`);
      for (const a of areas) {
        const item = el(
          `<div class="area-item"><div style="flex:1"><div>${esc(a.name)}</div><div class="meta">${a.tileCount.toLocaleString()} tiles · ${fmtBytes(a.sizeBytes)} · detail z${a.maxZoom}</div></div></div>`,
        );
        const go = el(`<button class="btn small" title="Go to area">⌖</button>`);
        go.addEventListener('click', () => this.tm.map.fitBounds(a.bounds as [number, number, number, number], { padding: 40 }));
        const x = el(`<button class="terr-x" title="Delete area">✕</button>`);
        x.addEventListener('click', async () => {
          if (!confirm(`Delete offline area "${a.name}"?`)) return;
          await removeArea(a);
          this.renderOfflinePanel();
        });
        item.append(go, x);
        sec.append(item);
      }
      p.append(sec);
    }
  }

  // ---------- project panel ----------

  async renderProjectPanel(): Promise<void> {
    const p = $('#panel-project');
    p.innerHTML = '';
    p.append(el(`<h3>Projects</h3>`));
    const projects = await listProjects();
    for (const proj of projects.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))) {
      const isCurrent = proj.id === this.project.id;
      const item = el(
        `<div class="terr-item ${isCurrent ? 'active' : ''}"><span style="flex:1;font-size:13px">${esc(proj.name)}</span><span class="terr-stats">${new Date(proj.updatedAt).toLocaleDateString()}</span></div>`,
      );
      if (!isCurrent) {
        item.addEventListener('click', () => {
          localStorage.setItem('tm-last-project', proj.id);
          location.reload();
        });
        const x = el(`<button class="terr-x" title="Delete project">✕</button>`);
        x.addEventListener('click', async (e) => {
          e.stopPropagation();
          if (!confirm(`Delete project "${proj.name}"?`)) return;
          await removeProject(proj.id);
          this.renderProjectPanel();
        });
        item.append(x);
      }
      p.append(item);
    }
    const newBtn = el(`<button class="btn">+ New project</button>`);
    newBtn.addEventListener('click', async () => {
      const proj = blankProject();
      await saveProject(proj);
      localStorage.setItem('tm-last-project', proj.id);
      location.reload();
    });
    const newRow = el(`<div class="row"></div>`);
    newRow.append(newBtn);
    p.append(newRow);

    const io = el(`<section><h3>Backup</h3><p class="hint">A project file contains everything: pins, territories, settings. Move it between devices or keep it with your records.</p></section>`);
    const exp = el(`<button class="btn small">Export project file</button>`);
    exp.addEventListener('click', () => {
      downloadText(JSON.stringify(this.project, null, 1), `${this.project.name}.tmproject.json`, 'application/json');
    });
    const impInput = el(`<input type="file" accept=".json,application/json" style="display:none" />`) as HTMLInputElement;
    const imp = el(`<button class="btn small">Import project file</button>`);
    imp.addEventListener('click', () => impInput.click());
    impInput.addEventListener('change', async () => {
      const f = impInput.files?.[0];
      if (!f) return;
      try {
        const proj = JSON.parse(await f.text()) as Project;
        if (!proj.territories || !proj.pinLayers) throw new Error('not a project file');
        proj.id = uid();
        proj.name = `${proj.name} (imported)`;
        await saveProject(proj);
        localStorage.setItem('tm-last-project', proj.id);
        location.reload();
      } catch {
        this.toast('That file is not a Territory Mapper project');
      }
    });
    const ioRow = el(`<div class="row"></div>`);
    ioRow.append(exp, imp, impInput);
    io.append(ioRow);
    p.append(io);

    p.append(
      el(
        `<section><h3>About</h3><p class="hint">Territory Mapper — free territory &amp; pin mapping for the US that works offline. Your data never leaves this device.<br><br>Map data © OpenStreetMap contributors · Tiles © OpenFreeMap · Boundaries &amp; population: US Census Bureau · Geocoding: US Census Bureau / Photon.<br><br>Tip: install this app — browser menu → “Install” / “Add to Home Screen”.</p></section>`,
      ),
    );
  }

  // ---------- legend & export ----------

  /** Legend content as data — shared by the on-screen legend and exports. */
  legendRows(): import('./exporter').LegendRow[] {
    const stats = computeStats(this.project, this.boundaries);
    const rows: import('./exporter').LegendRow[] = [];
    for (const t of this.project.territories) {
      const s = stats.get(t.id);
      rows.push({ color: t.color, label: t.name, meta: s ? `pop ${fmtNum(s.population)}` : undefined });
    }
    for (const layer of this.project.pinLayers) {
      if (!layer.visible || !layer.pins.length) continue;
      if (layer.colorBy) {
        rows.push({ color: null, label: `${layer.name} — ${layer.colorBy}` });
        let i = 0;
        const cats = this.categoryColors(layer);
        for (const [cat, color] of cats) {
          if (++i > 10) { rows.push({ color: null, label: `+${cats.size - 10} more` }); break; }
          rows.push({ color, label: cat || '(blank)', round: true });
        }
      } else {
        rows.push({ color: '#e15759', label: layer.name, meta: String(layer.pins.length), round: true });
      }
    }
    return rows;
  }

  renderLegend(): void {
    const legend = $('#legend');
    const stats = computeStats(this.project, this.boundaries);
    const parts: string[] = [];
    if (this.project.territories.length) {
      parts.push(`<h4>${esc(this.project.name)}</h4>`);
      for (const t of this.project.territories) {
        const s = stats.get(t.id);
        parts.push(
          `<div class="lrow"><span class="lswatch" style="background:${t.color}"></span><span>${esc(t.name)}</span><span class="lmeta">${s ? fmtNum(s.population) : ''}</span></div>`,
        );
      }
    }
    for (const layer of this.project.pinLayers) {
      if (!layer.visible || !layer.pins.length) continue;
      if (layer.colorBy) {
        parts.push(`<h4 style="margin-top:8px">${esc(layer.name)} — ${esc(layer.colorBy)}</h4>`);
        const cats = this.categoryColors(layer);
        let i = 0;
        for (const [cat, color] of cats) {
          if (++i > 10) { parts.push(`<div class="lrow"><span class="lmeta">+${cats.size - 10} more</span></div>`); break; }
          parts.push(`<div class="lrow"><span class="lswatch pin" style="background:${color}"></span><span>${esc(cat || '(blank)')}</span></div>`);
        }
      } else {
        parts.push(`<div class="lrow"><span class="lswatch pin" style="background:#e15759"></span><span>${esc(layer.name)}</span><span class="lmeta">${layer.pins.length}</span></div>`);
      }
    }
    legend.innerHTML = parts.join('');
    legend.hidden = parts.length === 0;
  }

  private openExportModal(): void {
    this.showModal(
      `<h3>Export map</h3>
       <div class="row"><label>Title</label><input type="text" id="exp-title" value="${escAttr(this.project.name)}" style="flex:1" /></div>
       <p class="hint">Exports the current map view with the legend, ready for reports and slides.</p>
       <div class="modal-actions">
         <button class="btn" data-close>Cancel</button>
         <button class="btn" id="exp-png">PNG image</button>
         <button class="btn primary" id="exp-pdf">PDF</button>
       </div>`,
    );
    const run = async (format: 'png' | 'pdf') => {
      const title = ($('#exp-title') as HTMLInputElement).value;
      this.closeModal();
      this.toast('Rendering export…');
      try {
        await exportMap(this.tm.map, { title, legend: this.legendRows(), format });
        this.toast(`${format.toUpperCase()} exported`);
      } catch (err) {
        console.error(err);
        this.toast('Export failed — see console');
      }
    };
    $('#exp-png').addEventListener('click', () => run('png'));
    $('#exp-pdf').addEventListener('click', () => run('pdf'));
  }

  // ---------- modal helpers ----------

  showModal(innerHtml: string): void {
    const modal = $('#modal') as HTMLDialogElement;
    modal.innerHTML = `<div class="modal-inner">${innerHtml}</div>`;
    modal.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => modal.close()));
    modal.showModal();
  }

  closeModal(): void {
    ($('#modal') as HTMLDialogElement).close();
  }
}

// ---------- helpers ----------

export function blankProject(): Project {
  return {
    id: uid(),
    name: 'My territory map',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    unitLevel: 'county',
    territories: [],
    assignments: {},
    pinLayers: [],
    mapView: { center: [-96.5, 39.5], zoom: 4 },
  };
}

function esc(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string);
}
function escAttr(s: string): string {
  return esc(s).replace(/'/g, '&#39;');
}
function fmtNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${Math.round(n / 1000)}K`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(Math.round(n));
}
