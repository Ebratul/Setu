import type { NextConfig } from "next";

// Local dev proxies /api/* to the FastAPI agent. Production routing is set up in Phase 8.1.
const agentUrl = process.env.AGENT_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${agentUrl}/:path*` }];
  },
};

export default nextConfig;
