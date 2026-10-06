import type { NextConfig } from "next";

// Where the FastAPI backend runs; the browser only ever talks to /api/backend.
const apiUrl = process.env.AUTORESILIENCE_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/backend/:path*", destination: `${apiUrl}/:path*` }];
  },
};

export default nextConfig;
