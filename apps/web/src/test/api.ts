/**
 * fetch-level API stub. Requests go through the real client (src/lib/api/client.ts),
 * so status handling and error mapping are production code. Bodies are typed with the
 * generated contract; any request without a handler fails the test.
 */
import { vi } from "vitest";

export type Request = { method: string; path: string; url: URL; body: unknown };
type Handler = (request: Request) => Response | Promise<Response>;

export const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

/** What the Next proxy answers when the API process is down: a bare 500. */
export const proxyDown = () => new Response("Internal Server Error", { status: 500 });

/** The browser could not reach anything (fetch rejects). */
export const networkError = (): never => {
  throw new TypeError("Failed to fetch");
};

/** FastAPI's error shape. */
export const apiError = (status: number, detail: unknown) => json({ detail }, status);

/** A response the test resolves later (in-flight requests, duplicate-submit checks). */
export function deferred() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((r) => (resolve = r));
  return { promise, resolve };
}

let unhandledInTest: string[] = [];

/** Called after each test (src/test/setup.ts): an unexpected request is a failure. */
export function assertNoUnhandledRequests() {
  const unexpected = unhandledInTest;
  unhandledInTest = [];
  if (unexpected.length) throw new Error(`Requests without a test handler: ${unexpected.join(", ")}`);
}

export function mockApi() {
  const handlers = new Map<string, Handler>();
  const requests: Request[] = [];
  const unhandled: string[] = (unhandledInTest = []);

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.pathname.replace(/^\/api\/backend/, "");
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    const request = { method, path, url, body };
    requests.push(request);
    const handler = handlers.get(`${method} ${path}`);
    if (!handler) {
      unhandled.push(`${method} ${path}`);
      return apiError(599, `No test handler for ${method} ${path}`);
    }
    return handler(request);
  });
  vi.stubGlobal("fetch", fetchMock);

  return {
    /** Register a handler; a plain value is sent as a 200 JSON body. */
    on(method: string, path: string, handler: Handler | object) {
      handlers.set(`${method} ${path}`, typeof handler === "function" ? (handler as Handler) : () => json(handler));
      return this;
    },
    /** Answer successive calls with successive handlers (the last one repeats). */
    sequence(method: string, path: string, ...steps: Handler[]) {
      let call = 0;
      handlers.set(`${method} ${path}`, (request) => steps[Math.min(call++, steps.length - 1)](request));
      return this;
    },
    requests: (method: string, path: string) => requests.filter((r) => r.method === method && r.path === path),
    unhandled,
  };
}
