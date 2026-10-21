import type { NextConfig } from "next";

// Local `make dev` proxies /api/* to the FastAPI agent. On Vercel, vercel.json routes /api/* to the agent service first, so this is never reached.
const agentUrl = process.env.AGENT_URL ?? "http://localhost:8000";

const agentPublic = process.env.NEXT_PUBLIC_AGENT_URL?.trim();
const isDev = process.env.NODE_ENV !== "production";

// Google sign-in is a top-level navigation started by the Neon SDK, so only form-action needs accounts.google.com.
// 'unsafe-inline' scripts: Next injects inline bootstrap/hydration scripts; a nonce would force every page dynamic.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  `connect-src 'self'${agentPublic ? ` ${agentPublic}` : ""}${isDev ? " ws: wss:" : ""}`,
  "frame-src 'self' blob:",
  "frame-ancestors 'self'",
  "base-uri 'self'",
  "form-action 'self' https://accounts.google.com",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
];

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
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${agentUrl}/:path*` }];
  },
};

export default nextConfig;
