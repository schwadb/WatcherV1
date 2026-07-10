// Territory assignment operations + the live stats rollup.
import type { Boundaries } from './boundaries';
import type { Project, TerritoryStats } from './types';

export const PALETTE = [
  '#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f', '#edc948',
  '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac', '#2f4b7c', '#a05195',
];

export function nextColor(project: Project): string {
  return PALETTE[project.territories.length % PALETTE.length];
}

export function newTerritoryName(project: Project): string {
  let n = project.territories.length + 1;
  const names = new Set(project.territories.map((t) => t.name));
  while (names.has(`Territory ${n}`)) n++;
  return `Territory ${n}`;
}

/** Assign a unit (fips) to a territory; pass null to unassign. Returns true if changed. */
export function assignUnit(project: Project, fips: string, territoryId: string | null): boolean {
  const prev = project.assignments[fips];
  if (territoryId === null) {
    if (prev === undefined) return false;
    delete project.assignments[fips];
    return true;
  }
  if (prev === territoryId) return false;
  project.assignments[fips] = territoryId;
  return true;
}

export function removeTerritory(project: Project, territoryId: string): void {
  project.territories = project.territories.filter((t) => t.id !== territoryId);
  for (const [fips, tid] of Object.entries(project.assignments)) {
    if (tid === territoryId) delete project.assignments[fips];
  }
}

/** The live rollup: population, unit count, pins, value sums per territory. */
export function computeStats(project: Project, boundaries: Boundaries): Map<string, TerritoryStats> {
  const stats = new Map<string, TerritoryStats>();
  for (const t of project.territories) {
    stats.set(t.id, { territoryId: t.id, unitCount: 0, population: 0, pinCount: 0, valueSums: {} });
  }
  const units = boundaries.units[project.unitLevel];
  for (const [fips, tid] of Object.entries(project.assignments)) {
    const s = stats.get(tid);
    const u = units.get(fips);
    if (!s || !u) continue;
    s.unitCount++;
    s.population += u.population;
  }
  // pins: match by county fips (state level: prefix)
  for (const layer of project.pinLayers) {
    if (!layer.visible) continue;
    for (const pin of layer.pins) {
      if (!pin.countyFips) continue;
      const unitFips = project.unitLevel === 'county' ? pin.countyFips : pin.countyFips.slice(0, 2);
      const tid = project.assignments[unitFips];
      if (!tid) continue;
      const s = stats.get(tid);
      if (!s) continue;
      s.pinCount++;
      if (layer.valueColumn) {
        const raw = pin.props[layer.valueColumn];
        const v = raw !== undefined ? parseFloat(String(raw).replace(/[$,%\s]/g, '').replace(/,/g, '')) : NaN;
        if (!Number.isNaN(v)) s.valueSums[layer.id] = (s.valueSums[layer.id] ?? 0) + v;
      }
    }
  }
  return stats;
}

/** Export assignments as CSV rows (the industry interchange format). */
export function assignmentsToCsv(project: Project, boundaries: Boundaries): string {
  const units = boundaries.units[project.unitLevel];
  const tName = new Map(project.territories.map((t) => [t.id, t.name]));
  const lines = [`${project.unitLevel === 'county' ? 'CountyFIPS' : 'StateFIPS'},Name,Territory`];
  const escape = (s: string) => (/[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
  for (const [fips, tid] of Object.entries(project.assignments).sort()) {
    const u = units.get(fips);
    const t = tName.get(tid);
    if (!u || !t) continue;
    lines.push(`${fips},${escape(u.name)},${escape(t)}`);
  }
  return lines.join('\n');
}

/**
 * Import a FIPS→Territory CSV (creates territories by name as needed).
 * Returns number of assignments applied.
 */
export function importAssignments(
  project: Project,
  rows: Array<Record<string, string>>,
  makeId: () => string,
): number {
  const byName = new Map(project.territories.map((t) => [t.name.toLowerCase(), t]));
  let applied = 0;
  for (const row of rows) {
    const keys = Object.keys(row);
    const fipsKey = keys.find((k) => /fips|geoid|code/i.test(k)) ?? keys[0];
    const terrKey = keys.find((k) => /territor|region|group|rep|owner/i.test(k)) ?? keys[keys.length - 1];
    let fips = (row[fipsKey] ?? '').trim();
    const terr = (row[terrKey] ?? '').trim();
    if (!fips || !terr) continue;
    fips = fips.padStart(project.unitLevel === 'county' ? 5 : 2, '0');
    let t = byName.get(terr.toLowerCase());
    if (!t) {
      t = { id: makeId(), name: terr, color: PALETTE[byName.size % PALETTE.length] };
      project.territories.push(t);
      byName.set(terr.toLowerCase(), t);
    }
    project.assignments[fips] = t.id;
    applied++;
  }
  return applied;
}
