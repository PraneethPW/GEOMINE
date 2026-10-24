export type Geometry =
  | { type: "Polygon"; coordinates: number[][][] }
  | { type: "MultiPolygon"; coordinates: number[][][][] };
export type Area = {
  id: string;
  name: string;
  geometry: Geometry;
  area_km2: number;
  monitoring: boolean;
  interval_hours: number;
  next_run_at: string | null;
};
export type User = {
  id: string;
  name: string;
  email: string;
  email_verified?: boolean;
};
export type System = {
  database: string;
  radar_access: boolean;
  radar_provider: string;
  radar_coverage: string;
  analysis_resolution_m: number;
  ai: boolean;
  model_available: boolean;
  registration: boolean;
  authentication?: string;
  max_aoi_km2: number;
};
export type Scene = {
  id: string;
  datetime: string;
  cloud_cover: number | null;
  platform: string;
  geometry: Geometry;
  sensor: "optical" | "radar";
  catalog_url: string;
};
export type Job = {
  id: string;
  area_id: string;
  area_name?: string;
  engine: string;
  status: string;
  stage: string;
  progress: number;
  error: string | null;
  created_at: string;
  finished_at?: string | null;
  before_start: string;
  before_end: string;
  after_start: string;
  after_end: string;
  result: null | {
    candidate_count: number;
    area_ha: number;
    quality: { clear_optical_fraction: number; radar_valid_fraction: number };
    scenes: {
      id: string;
      collection: string;
      datetime: string;
      catalog_url?: string;
    }[];
    resolution_m: number;
    radar_source: string;
    limitations: string[];
    engine: string;
    score_type: string;
  };
};
export type Alert = {
  id: string;
  area_id: string;
  job_id: string;
  area_name: string;
  geometry: Geometry;
  area_ha: number;
  score: number;
  legal_context: string;
  status: string;
  note: string;
  created_at: string;
};
export type Concession = {
  id: string;
  name: string;
  authority: string;
  source_url: string;
  valid_from: string;
  valid_to: string;
  geometry: Geometry;
};
export type Brief = {
  id: string;
  job_id: string;
  model: string;
  content: string;
  created_at: string;
};
export type Audit = {
  id: number;
  action: string;
  resource_id: string;
  created_at: string;
};
const configured =
  (import.meta as unknown as { env: Record<string, string> }).env.VITE_API_URL || "";
export const API = configured.replace(/\/$/, "");
export function token() {
  return sessionStorage.getItem("geomine.session") || "";
}
export function setToken(value: string) {
  value
    ? sessionStorage.setItem("geomine.session", value)
    : sessionStorage.removeItem("geomine.session");
}
export async function accessToken() {
  const value = token();
  if (value.split(".").length !== 3) return value;
  const { freshManagedToken } = await import("./managedIdentity");
  try {
    const fresh = await freshManagedToken();
    setToken(fresh);
    return fresh;
  } catch (error) {
    const code =
      typeof error === "object" && error && "code" in error ? String(error.code) : "";
    if (
      [
        "auth/user-token-expired",
        "auth/invalid-user-token",
        "auth/user-disabled",
      ].includes(code)
    ) {
      setToken("");
      window.dispatchEvent(new Event("geomine:session-expired"));
      throw new ApiError("Your session has expired. Sign in again.", 401);
    }
    throw error;
  }
}
export async function endSession() {
  try {
    if (token().split(".").length === 3) {
      const { managedAuth } = await import("./managedIdentity");
      await (await managedAuth()).signOut();
    }
  } catch {
    // A provider outage must not prevent clearing this browser's app session.
  } finally {
    setToken("");
  }
}
export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const bearer = await accessToken();
  const response = await fetch(`${API}/api${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    if (response.status === 401 && !["/auth/firebase", "/auth/login"].includes(path)) {
      setToken("");
      window.dispatchEvent(new Event("geomine:session-expired"));
    }
    let message = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      message =
        typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* non-JSON provider error */
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}
export async function downloadJob(id: string) {
  const res = await fetch(`${API}/api/jobs/${id}/export`, {
    headers: { Authorization: `Bearer ${await accessToken()}` },
  });
  if (!res.ok) throw new Error("Unable to export this analysis.");
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `geomine-${id}.geojson`;
  a.click();
  URL.revokeObjectURL(url);
}
export function dateOffset(days: number) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
export function rectangle(lon: number, lat: number, radius = 0.02): Geometry {
  return {
    type: "Polygon",
    coordinates: [
      [
        [lon - radius, lat - radius],
        [lon + radius, lat - radius],
        [lon + radius, lat + radius],
        [lon - radius, lat + radius],
        [lon - radius, lat - radius],
      ],
    ],
  };
}
export function center(geometry: Geometry): [number, number] {
  const coords =
    geometry.type === "Polygon"
      ? geometry.coordinates[0]
      : geometry.coordinates.flatMap((polygon) => polygon[0]);
  return [
    (Math.min(...coords.map((c) => c[0])) + Math.max(...coords.map((c) => c[0]))) / 2,
    (Math.min(...coords.map((c) => c[1])) + Math.max(...coords.map((c) => c[1]))) / 2,
  ];
}
