// Core data model. A Project is the unit of persistence — everything the user
// makes lives in one Project object, autosaved to IndexedDB.

export interface Project {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  /** 'state' or 'county' — the building block territories are made of */
  unitLevel: UnitLevel;
  territories: Territory[];
  /** FIPS code -> territory id. Single source of truth for assignment. */
  assignments: Record<string, string>;
  pinLayers: PinLayer[];
  mapView: { center: [number, number]; zoom: number };
}

export type UnitLevel = 'state' | 'county';

export interface Territory {
  id: string;
  name: string;
  color: string;
}

export interface PinLayer {
  id: string;
  name: string;
  visible: boolean;
  /** column name used to color-group pins, if any */
  colorBy: string | null;
  /** column name summed into territory stats, if any (e.g. "Sales") */
  valueColumn: string | null;
  pins: Pin[];
}

export interface Pin {
  id: string;
  lng: number;
  lat: number;
  /** original row from the imported spreadsheet */
  props: Record<string, string>;
  /** FIPS of the county containing this pin (computed on import) */
  countyFips: string | null;
  /** geocode provenance: 'coords' = lat/lon in file, 'census' = geocoded */
  source: 'coords' | 'census';
}

/** Live rollup shown while editing — the "AlignMix moment". */
export interface TerritoryStats {
  territoryId: string;
  unitCount: number;
  population: number;
  pinCount: number;
  /** sum of each pin layer's valueColumn, keyed by layer id */
  valueSums: Record<string, number>;
}

export interface OfflineArea {
  id: string;
  name: string;
  bounds: [number, number, number, number]; // w, s, e, n
  minZoom: number;
  maxZoom: number;
  tileCount: number;
  sizeBytes: number;
  createdAt: string;
}
