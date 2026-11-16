/**
 * Fetch wrapper for the Station REST API (docs/spec/station.md §5.1): JSON, the HttpOnly `hst`
 * cookie (same origin), `X-Station: 1` on every non-GET request, and RFC 9457 Problem errors.
 */
import type { Problem } from "./types";

export const STATION_API = "/api/v1";

export function stationBase(): string {
  return `${window.location.origin}${STATION_API}`;
}

export function stationWsUrl(path: "/ws" | "/ws/video"): string {
  const { protocol, host } = window.location;
  return `${protocol === "https:" ? "wss:" : "ws:"}//${host}${STATION_API}${path}`;
}

export class StationApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly problem: Problem | null;
  /** The response body when it was not a Problem (a proxy page, FastAPI's `{"detail": ...}`). */
  readonly raw: string;

  constructor(status: number, problem: Problem | null, fallbackCode = "unknown_error", raw = "") {
    super(problem?.detail ?? problem?.title ?? `HTTP ${status}`);
    this.name = "StationApiError";
    this.status = status;
    this.problem = problem;
    this.code = problem?.code ?? fallbackCode;
    this.raw = raw;
  }

  get params(): Record<string, unknown> {
    return this.problem?.params ?? {};
  }
}

function isProblem(v: unknown): v is Problem {
  if (typeof v !== "object" || v === null) return false;
  const o = v as Record<string, unknown>;
  return typeof o.code === "string" && typeof o.status === "number";
}

export interface RequestOptions {
  body?: unknown;
  query?: Record<string, string | number | undefined>;
  signal?: AbortSignal;
}

export async function stationFetch<T>(
  method: "GET" | "POST" | "PUT" | "DELETE",
  path: string,
  { body, query, signal }: RequestOptions = {},
): Promise<T> {
  const url = new URL(`${stationBase()}${path}`);
  for (const [k, v] of Object.entries(query ?? {})) if (v !== undefined) url.searchParams.set(k, String(v));
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") headers["X-Station"] = "1";
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers,
      credentials: "same-origin",
      ...(payload !== undefined ? { body: payload } : {}),
      ...(signal ? { signal } : {}),
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new StationApiError(0, null, "network_error");
  }
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!res.ok) {
    if (isProblem(data)) throw new StationApiError(res.status, data);
    const d = (data as { detail?: unknown } | null)?.detail;
    const raw = typeof d === "string" ? d : d !== undefined ? JSON.stringify(d) : text;
    throw new StationApiError(res.status, null, "unknown_error", raw.slice(0, 500));
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, opts?: RequestOptions) => stationFetch<T>("GET", path, opts),
  post: <T>(path: string, body: unknown = {}, opts?: RequestOptions) =>
    stationFetch<T>("POST", path, { ...opts, body }),
  put: <T>(path: string, body: unknown, opts?: RequestOptions) =>
    stationFetch<T>("PUT", path, { ...opts, body }),
  del: (path: string, opts?: RequestOptions) => stationFetch<undefined>("DELETE", path, opts),
};
