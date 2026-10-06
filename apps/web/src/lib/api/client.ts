/**
 * Typed client for the AutoResilience FastAPI backend.
 *
 * The browser calls `/api/backend/*`; next.config.ts rewrites that to the API
 * (AUTORESILIENCE_API_URL, default http://localhost:8000), so no CORS is needed.
 */
import type {
  AbortRequest,
  Experiment,
  ExperimentCreate,
  Health,
  Score,
} from "./types";

export const API_BASE_PATH = "/api/backend";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    readonly path: string,
    /** No usable API response: network failure, or a 5xx without a JSON body. */
    readonly unavailable = false,
  ) {
    super(
      unavailable
        ? `No valid response from the API${status ? ` (HTTP ${status})` : ""}. ` +
            "Check that the backend is running at the URL shown in Settings."
        : `${status} ${detail}`,
    );
    this.name = "ApiError";
  }
}

function detailOf(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      // FastAPI 422: [{loc: [...], msg: "..."}]
      return detail
        .map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d)))
        .join("; ");
    }
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_PATH}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch (error) {
    throw new ApiError(0, (error as Error).message, path, true);
  }
  const text = await response.text();
  let body: unknown = undefined;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!response.ok) {
    // FastAPI errors are JSON ({"detail": ...}); a bare 5xx means the proxy or a
    // crashed process answered instead of the API.
    const unavailable = response.status >= 500 && (body === undefined || typeof body === "string");
    throw new ApiError(response.status, detailOf(body, response.statusText), path, unavailable);
  }
  return body as T;
}

function post<T>(path: string, payload?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
}

export const api = {
  health: () => request<Health>("/health"),
  listExperiments: () => request<Experiment[]>("/experiments"),
  getExperiment: (id: string) => request<Experiment>(`/experiments/${encodeURIComponent(id)}`),
  getScore: (id: string, version?: string) =>
    request<Score>(
      `/experiments/${encodeURIComponent(id)}/score` +
        (version ? `?version=${encodeURIComponent(version)}` : ""),
    ),
  createExperiment: (payload: ExperimentCreate) => post<Experiment>("/experiments", payload),
  runExperiment: (id: string) => post<Experiment>(`/experiments/${encodeURIComponent(id)}/run`),
  abortExperiment: (id: string, payload: AbortRequest) =>
    post<Experiment>(`/experiments/${encodeURIComponent(id)}/abort`, payload),
};
