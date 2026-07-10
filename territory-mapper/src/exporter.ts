// Export the current map view + legend as PNG or PDF.
// The legend is drawn directly on the canvas (DOM rasterization is flaky in
// some engines); the map is captured only after all tiles finish loading.
import { jsPDF } from 'jspdf';
import type maplibregl from 'maplibre-gl';

const MAX_DIM = 4096; // iOS-safe canvas ceiling

export interface LegendRow {
  /** swatch color; null renders a section heading instead */
  color: string | null;
  label: string;
  meta?: string;
  round?: boolean;
}

export interface ExportOptions {
  title: string;
  legend: LegendRow[];
  format: 'png' | 'pdf';
}

function waitForTiles(map: maplibregl.Map, timeoutMs = 10_000): Promise<void> {
  if (map.loaded() && map.areTilesLoaded()) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(), timeoutMs);
    map.once('idle', () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

function drawLegend(ctx: CanvasRenderingContext2D, rows: LegendRow[], x: number, y: number, scale: number): void {
  if (!rows.length) return;
  const pad = 14 * scale;
  const rowH = 22 * scale;
  const headH = 26 * scale;
  const swatch = 13 * scale;
  const fontBody = `${Math.round(13 * scale)}px system-ui, sans-serif`;
  const fontHead = `600 ${Math.round(14 * scale)}px system-ui, sans-serif`;

  // measure
  let w = 0;
  let h = pad * 2;
  for (const r of rows) {
    ctx.font = r.color === null ? fontHead : fontBody;
    const tw = ctx.measureText(r.label).width + (r.meta ? ctx.measureText(r.meta).width + 26 * scale : 0);
    w = Math.max(w, (r.color === null ? 0 : swatch + 8 * scale) + tw);
    h += r.color === null ? headH : rowH;
  }
  w += pad * 2;

  // panel
  const yTop = y - h;
  ctx.save();
  ctx.shadowColor = 'rgba(0,0,0,0.22)';
  ctx.shadowBlur = 10 * scale;
  ctx.fillStyle = '#ffffff';
  ctx.beginPath();
  ctx.roundRect(x, yTop, w, h, 10 * scale);
  ctx.fill();
  ctx.restore();

  // rows
  let cy = yTop + pad;
  ctx.textBaseline = 'middle';
  for (const r of rows) {
    if (r.color === null) {
      ctx.font = fontHead;
      ctx.fillStyle = '#111827';
      ctx.fillText(r.label, x + pad, cy + headH / 2);
      cy += headH;
    } else {
      ctx.fillStyle = r.color;
      const sy = cy + (rowH - swatch) / 2;
      ctx.beginPath();
      if (r.round) ctx.arc(x + pad + swatch / 2, sy + swatch / 2, swatch / 2, 0, Math.PI * 2);
      else ctx.roundRect(x + pad, sy, swatch, swatch, 3 * scale);
      ctx.fill();
      ctx.font = fontBody;
      ctx.fillStyle = '#1f2937';
      ctx.fillText(r.label, x + pad + swatch + 8 * scale, cy + rowH / 2);
      if (r.meta) {
        ctx.fillStyle = '#6b7280';
        ctx.fillText(r.meta, x + pad + swatch + 8 * scale + ctx.measureText(r.label).width + 14 * scale, cy + rowH / 2);
      }
      cy += rowH;
    }
  }
}

async function composeCanvas(map: maplibregl.Map, opts: ExportOptions): Promise<HTMLCanvasElement> {
  await waitForTiles(map);

  const mapCanvas = map.getCanvas();
  const headerH = opts.title ? 96 : 0;
  const footerH = 44;
  let w = mapCanvas.width;
  let h = mapCanvas.height + headerH + footerH;
  const scale = Math.min(1, MAX_DIM / w, MAX_DIM / h);
  w = Math.floor(w * scale);
  h = Math.floor(h * scale);

  const out = document.createElement('canvas');
  out.width = w;
  out.height = h;
  const ctx = out.getContext('2d')!;
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, w, h);

  // capture the map synchronously inside a fresh render frame
  await new Promise<void>((resolve) => {
    map.once('render', () => {
      ctx.drawImage(mapCanvas, 0, headerH * scale, mapCanvas.width * scale, mapCanvas.height * scale);
      resolve();
    });
    map.triggerRepaint();
  });

  if (opts.title) {
    ctx.fillStyle = '#111827';
    ctx.font = `600 ${Math.round(40 * scale)}px system-ui, sans-serif`;
    ctx.textBaseline = 'middle';
    ctx.fillText(opts.title, Math.round(28 * scale), Math.round((headerH * scale) / 2));
  }

  drawLegend(ctx, opts.legend, 16 * scale, headerH * scale + mapCanvas.height * scale - 16 * scale, scale);

  ctx.fillStyle = '#6b7280';
  ctx.font = `${Math.round(20 * scale)}px system-ui, sans-serif`;
  ctx.textBaseline = 'middle';
  ctx.fillText(
    `Made with Territory Mapper • Map data © OpenStreetMap contributors, tiles © OpenFreeMap • ${new Date().toLocaleDateString()}`,
    Math.round(28 * scale),
    h - (footerH * scale) / 2,
  );
  return out;
}

export async function exportMap(map: maplibregl.Map, opts: ExportOptions): Promise<void> {
  const canvas = await composeCanvas(map, opts);
  const safeName = (opts.title || 'map').replace(/[^\w\- ]+/g, '').trim().replace(/\s+/g, '-') || 'map';

  if (opts.format === 'png') {
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
    if (!blob) throw new Error('PNG encoding failed');
    triggerDownload(URL.createObjectURL(blob), `${safeName}.png`);
    return;
  }

  const landscape = canvas.width >= canvas.height;
  const pdf = new jsPDF({ orientation: landscape ? 'landscape' : 'portrait', unit: 'pt', format: 'letter' });
  const pw = pdf.internal.pageSize.getWidth();
  const ph = pdf.internal.pageSize.getHeight();
  const margin = 24;
  const fit = Math.min((pw - margin * 2) / canvas.width, (ph - margin * 2) / canvas.height);
  const iw = canvas.width * fit;
  const ih = canvas.height * fit;
  pdf.addImage(canvas.toDataURL('image/jpeg', 0.92), 'JPEG', (pw - iw) / 2, (ph - ih) / 2, iw, ih);
  pdf.save(`${safeName}.pdf`);
}

function triggerDownload(url: string, filename: string): void {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

/** Download a text file (CSV / project JSON). */
export function downloadText(content: string, filename: string, mime = 'text/plain'): void {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  triggerDownload(URL.createObjectURL(blob), filename);
}
