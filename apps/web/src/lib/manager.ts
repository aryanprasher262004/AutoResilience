/**
 * Client for the loopback service manager (`ar manager`, tools/ar/ar_cli/manager.py, D-4).
 *
 * The browser calls it directly on 127.0.0.1 (it is not proxied: the console container
 * cannot reach the host). The manager accepts only this console's origin, a pairing
 * token printed in its terminal, JSON bodies, and allowlisted operations, each of which
 * needs a confirmation id from its plan. The token is kept in sessionStorage for this
 * tab only.
 */
export const DEFAULT_MANAGER_PORT = 8765;
const STORAGE_KEY = "autoresilience.manager";

export type Pairing = { port: number; token: string };

export type ManagerOperation = { name: string; title: string; plan: string[] };
export type ManagerPlan = {
  operation: string;
  title: string;
  plan: string[];
  confirmation: string;
  expires_in_seconds: number;
};
export type ManagerJob = {
  id: string;
  operation: string;
  state: "running" | "succeeded" | "failed";
  output: string[];
  started_at: number;
  finished_at: number | null;
};

export class ManagerError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ManagerError";
  }
}

export function loadPairing(): Pairing | null {
  try {
    const raw = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "null") as unknown;
    if (raw && typeof raw === "object" && "port" in raw && "token" in raw) {
      const { port, token } = raw as Pairing;
      if (Number.isInteger(port) && typeof token === "string" && token) return { port, token };
    }
  } catch {
    // unavailable storage or malformed value: not paired
  }
  return null;
}

export function savePairing(pairing: Pairing | null) {
  try {
    if (pairing) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(pairing));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // storage blocked: pairing lasts for this page only
  }
}

async function call<T>(pairing: Pairing, method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`http://127.0.0.1:${pairing.port}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${pairing.token}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new ManagerError(
      `No service manager on 127.0.0.1:${pairing.port}. Start it in a terminal: python3 tools/ar/ar.py manager`,
      0,
    );
  }
  const data = (await response.json().catch(() => null)) as { detail?: string } | null;
  if (!response.ok) throw new ManagerError(data?.detail ?? `HTTP ${response.status}`, response.status);
  return data as T;
}

export const manager = {
  status: (p: Pairing) => call<Record<string, unknown>>(p, "GET", "/v1/status"),
  operations: (p: Pairing) => call<{ items: ManagerOperation[] }>(p, "GET", "/v1/operations"),
  plan: (p: Pairing, name: string) => call<ManagerPlan>(p, "POST", `/v1/operations/${encodeURIComponent(name)}/plan`, {}),
  run: (p: Pairing, name: string, confirmation: string) =>
    call<ManagerJob>(p, "POST", `/v1/operations/${encodeURIComponent(name)}`, { confirmation }),
  job: (p: Pairing, id: string) => call<ManagerJob>(p, "GET", `/v1/jobs/${encodeURIComponent(id)}`),
};

/** A one-line reading of `ar status --json` (the manager's /v1/status); missing fields stay unknown. */
export function summarizeStatus(status: Record<string, unknown>): { label: string; value: string; ok: boolean | null }[] {
  const obj = (v: unknown) => (v && typeof v === "object" ? (v as Record<string, unknown>) : {});
  const cluster = obj(status.cluster);
  const services = obj(status.services);
  const api = obj(status.api);
  const consoleInfo = obj(status.console);
  const svc = (name: string) => {
    const s = obj(services[name]);
    if (!("state" in s)) return { value: "no container", ok: false };
    return { value: `${String(s.state)}${s.health ? ` (${String(s.health)})` : ""}`, ok: s.state === "running" };
  };
  return [
    { label: "Docker", value: String(status.docker ?? "unknown"), ok: status.docker === "running" },
    {
      label: "Cluster node",
      value: "running" in cluster ? (cluster.running ? "running" : "stopped") : "unknown",
      ok: "running" in cluster ? cluster.running === true : null,
    },
    { label: "Database", ...svc("postgres") },
    { label: "Engine", ...svc("api") },
    { label: "Console", ...svc("web") },
    {
      label: "Engine /ready",
      value: api.ready_http === undefined ? "unknown" : String(api.ready_http ?? "no answer"),
      ok: api.ready_http === undefined ? null : api.ready_http === 200,
    },
    {
      label: "Console reachable",
      value: consoleInfo.reachable === undefined ? "unknown" : consoleInfo.reachable ? "yes" : "no",
      ok: consoleInfo.reachable === undefined ? null : consoleInfo.reachable === true,
    },
  ];
}
