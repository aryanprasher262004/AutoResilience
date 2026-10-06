import type { NextConfig } from "next";

// Where the FastAPI backend runs; the browser only ever talks to /api/backend.
// Rewrites are resolved at build time (`next build` / `next dev`), so set
// AUTORESILIENCE_API_URL before building; changing it for `next start` alone has no effect.
const apiUrl = process.env.AUTORESILIENCE_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Exposes the proxy target actually baked into this build (shown on /settings).
  env: { AUTORESILIENCE_API_PROXY_TARGET: apiUrl },
  async rewrites() {
    return [{ source: "/api/backend/:path*", destination: `${apiUrl}/:path*` }];
  },
};

export default nextConfig;
