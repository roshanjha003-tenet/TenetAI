import type { NextConfig } from "next";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";
const apiOrigin = new URL(api).origin;
const dev = process.env.NODE_ENV !== "production";

// The page may talk only to Tenet's API; no framing, no plugins, no foreign scripts.
const csp = [
  "default-src 'self'",
  `connect-src 'self' ${apiOrigin}`,
  `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https:",
  "font-src 'self' data:",
  "object-src 'none'",
  "base-uri 'self'",
  `form-action 'self' ${apiOrigin}`,
  "frame-ancestors 'none'",
].join("; ");

const config: NextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default config;
