// Load bundled us-atlas TopoJSON and expose GeoJSON + lookup helpers.
import { feature } from 'topojson-client';
import type { Topology, GeometryCollection } from 'topojson-specification';
import { geomBBox, pointInFeature, type BBox } from './geo';
import type { UnitLevel } from './types';

export interface UnitInfo {
  fips: string;
  name: string;
  /** for counties: the parent state fips (first 2 chars) */
  stateFips: string;
  population: number;
}

export interface Boundaries {
  states: GeoJSON.FeatureCollection;
  counties: GeoJSON.FeatureCollection;
  units: Record<UnitLevel, Map<string, UnitInfo>>;
  countyOf(pt: [number, number]): string | null;
}

const STATE_NAMES: Record<string, string> = {}; // filled from states file

let cached: Boundaries | null = null;

export async function loadBoundaries(): Promise<Boundaries> {
  if (cached) return cached;
  const [statesTopo, countiesTopo, countyPop] = await Promise.all([
    fetch(`${import.meta.env.BASE_URL}data/states.json`).then((r) => r.json() as Promise<Topology>),
    fetch(`${import.meta.env.BASE_URL}data/counties.json`).then((r) => r.json() as Promise<Topology>),
    fetch(`${import.meta.env.BASE_URL}data/county-population.json`).then((r) => r.json() as Promise<Record<string, number>>),
  ]);

  const states = feature(statesTopo, statesTopo.objects.states as GeometryCollection) as unknown as GeoJSON.FeatureCollection;
  const counties = feature(countiesTopo, countiesTopo.objects.counties as GeometryCollection) as unknown as GeoJSON.FeatureCollection;

  // numeric ids for feature-state (FIPS strings cast cleanly to ints)
  for (const f of states.features) {
    const fips = String(f.id).padStart(2, '0');
    f.id = parseInt(fips, 10);
    f.properties = { ...f.properties, fips };
    STATE_NAMES[fips] = (f.properties as { name?: string }).name ?? fips;
  }
  const countyInfo = new Map<string, UnitInfo>();
  const statePop = new Map<string, number>();
  const countyBBoxes: Array<{ fips: string; bbox: BBox; feat: GeoJSON.Feature }> = [];
  for (const f of counties.features) {
    const fips = String(f.id).padStart(5, '0');
    f.id = parseInt(fips, 10);
    const stateFips = fips.slice(0, 2);
    const pop = countyPop[fips] ?? 0;
    const name = (f.properties as { name?: string }).name ?? fips;
    f.properties = { ...f.properties, fips, label: `${name}${STATE_NAMES[stateFips] ? ', ' + STATE_NAMES[stateFips] : ''}` };
    countyInfo.set(fips, { fips, name, stateFips, population: pop });
    statePop.set(stateFips, (statePop.get(stateFips) ?? 0) + pop);
    if (f.geometry) countyBBoxes.push({ fips, bbox: geomBBox(f.geometry), feat: f });
  }
  const stateInfo = new Map<string, UnitInfo>();
  for (const f of states.features) {
    const fips = (f.properties as { fips: string }).fips;
    stateInfo.set(fips, {
      fips,
      name: (f.properties as { name?: string }).name ?? fips,
      stateFips: fips,
      population: statePop.get(fips) ?? 0,
    });
  }

  cached = {
    states,
    counties,
    units: { state: stateInfo, county: countyInfo },
    countyOf(pt) {
      for (const c of countyBBoxes) {
        const [w, s, e, n] = c.bbox;
        if (pt[0] < w || pt[0] > e || pt[1] < s || pt[1] > n) continue;
        if (c.feat.geometry && pointInFeature(pt, c.feat.geometry)) return c.fips;
      }
      return null;
    },
  };
  return cached;
}
