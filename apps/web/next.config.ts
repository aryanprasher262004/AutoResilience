import path from "node:path";

import type { NextConfig } from "next";

import packageJson from "./package.json" with { type: "json" };

// Where the FastAPI backend runs; the browser only ever talks to /api/backend.
// Rewrites are resolved at build time (`next build` / `next dev`), so set
// AUTORESILIENCE_API_URL before building; changing it for `next start` alone has no effect.
const apiUrl = process.env.AUTORESILIENCE_API_URL ?? "http://localhost:8000";
// The local-stack image (apps/web/Dockerfile) runs the self-contained server; `next start`
// and `next dev` keep the default output.
const standalone = process.env.AUTORESILIENCE_STANDALONE === "1";

const nextConfig: NextConfig = {
  transpilePackages: ["@autoresilience/ui"],
  ...(standalone
    ? // Trace from the workspace root so packages/ui and hoisted node_modules are included.
      { output: "standalone" as const, outputFileTracingRoot: path.resolve(process.cwd(), "../..") }
    : {}),
  // Exposes the proxy target actually baked into this build (shown on /settings).
  env: { AUTORESILIENCE_API_PROXY_TARGET: apiUrl, AUTORESILIENCE_CONSOLE_VERSION: packageJson.version },
  async rewrites() {
    return [{ source: "/api/backend/:path*", destination: `${apiUrl}/:path*` }];
  },
};

export default nextConfig;
