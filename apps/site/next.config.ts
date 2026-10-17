import type { NextConfig } from "next";

// Public website: a static export (plain files in out/). Static export cannot run rewrites,
// headers, a proxy or route handlers, so this site has no path to the engine API by
// construction; scripts/check-static.mjs verifies the build output stays that way.
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  transpilePackages: ["@autoresilience/ui"],
};

export default nextConfig;
