/**
 * Typed client for the AutoResilience FastAPI backend.
 *
 * The browser calls `/api/backend/*`; next.config.ts rewrites that to the API
 * (AUTORESILIENCE_API_URL, default http://localhost:8000), so no CORS is needed.
 */
import type {
  AbortRequest,
  DashboardSummary,
  Experiment,
  ExperimentCreate,
  ExperimentPage,
  Health,
  HistoryQuery,
  Readiness,
  Score,
  ServiceDetail,
  ServiceList,
  WorkloadKind,
} from "./types";

function toSearch(query: HistoryQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === "" || (Array.isArray(value) && !value.length)) continue;
    for (const v of Array.isArray(value) ? value : [value]) params.append(key, String(v));
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

export const API_BASE_PATH = "/api/backend";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    readonly path: string,
    /** No usable API response: network failure, or a 5xx without a JSON body. */
    readonly unavailable = false,
    /** Parsed response body, e.g. FastAPI 422 details with field locations. */
    readonly body: unknown = undefined,
  ) {
    super(
      unavailable
        ? `No valid response from the API${status ? ` (HTTP ${status})` : ""}. ` +
            "Check that the backend is running at the URL shown in Settings."
        : `${status} ${detail}`,
    );
    this.name = "ApiError";
  }

  /** FastAPI 422 errors keyed by body path, e.g. "target.namespace" -> message. */
  fieldErrors(): Record<string, string> {
    if (this.status !== 422 || !this.body || typeof this.body !== "object") return {};
    const detail = (this.body as { detail?: unknown }).detail;
    if (!Array.isArray(detail)) return {};
    const errors: Record<string, string> = {};
    for (const item of detail) {
      if (!item || typeof item !== "object") continue;
      const { loc, msg } = item as { loc?: unknown; msg?: unknown };
      if (!Array.isArray(loc) || typeof msg !== "string") continue;
      const key = loc.filter((part) => part !== "body").join(".");
      errors[key] ??= msg;
    }
    return errors;
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
    throw new ApiError(
      response.status,
      detailOf(body, response.statusText),
      path,
      unavailable,
      body,
    );
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

function isReadiness(body: unknown): body is Readiness {
  return !!body && typeof body === "object" && "status" in body && "checks" in body;
}

export const api = {
  health: () => request<Health>("/health"),
  /** 503 "not_ready" is an answer, not a failure: it is returned as data. */
  readiness: async (): Promise<Readiness> => {
    try {
      return await request<Readiness>("/ready");
    } catch (error) {
      if (error instanceof ApiError && error.status === 503 && isReadiness(error.body)) return error.body;
      throw error;
    }
  },
  listExperiments: () => request<Experiment[]>("/experiments"),
  history: (query: HistoryQuery) => request<ExperimentPage>(`/experiments/history${toSearch(query)}`),
  dashboard: () => request<DashboardSummary>("/dashboard/summary"),
  services: () => request<ServiceList>("/services"),
  service: (namespace: string, kind: WorkloadKind, name: string) =>
    request<ServiceDetail>(
      `/services/${encodeURIComponent(namespace)}/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`,
    ),
  getExperiment: (id: string) => request<Experiment>(`/experiments/${encodeURIComponent(id)}`),
  getScore: (id: string, version?: string) =>
    request<Score>(
      `/experiments/${encodeURIComponent(id)}/score` +
        (version ? `?version=${encodeURIComponent(version)}` : ""),
    ),
  createExperiment: (payload: ExperimentCreate) => post<Experiment>("/experiments", payload),
  validateExperiment: (id: string) =>
    post<Experiment>(`/experiments/${encodeURIComponent(id)}/validate`),
  runExperiment: (id: string) => post<Experiment>(`/experiments/${encodeURIComponent(id)}/run`),
  abortExperiment: (id: string, payload: AbortRequest) =>
    post<Experiment>(`/experiments/${encodeURIComponent(id)}/abort`, payload),
};
