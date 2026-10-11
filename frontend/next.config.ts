import type { NextConfig } from "next";

const backendOrigin = (
  process.env.VEDNIX_BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : "https://vednix.onrender.com")
).trim().replace(/\/$/, "");

// The WebSocket chat transport talks to the backend origin directly (the HTTP
// API is proxied same-origin through the rewrites below), so the CSP must allow
// both the http(s) and ws(s) form of it — plus the loopback dev endpoints.
const backendWsOrigin = backendOrigin.replace(/^http/, "ws");
const connectSrc = Array.from(new Set([
  "'self'",
  backendOrigin,
  backendWsOrigin,
  "https://vednix.onrender.com",
  "wss://vednix.onrender.com",
  "http://localhost:8000",
  "ws://localhost:8000",
  "http://127.0.0.1:8000",
  "ws://127.0.0.1:8000",
  ...(process.env.NEXT_PUBLIC_CSP_CONNECT_EXTRA ?? "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean),
])).join(" ");

// Baseline hardening headers for every response. `script-src`/`style-src` keep
// 'unsafe-inline' because Next.js injects inline bootstrap/hydration scripts —
// a nonce-based CSP needs request middleware and would need nonce propagation
// into the RSC payload; the app renders no user-supplied HTML (react-markdown
// without rehype-raw, mermaid at securityLevel "strict"), so the exposure this
// leaves is dependency-level, not application-level.
const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src " + connectSrc,
  "media-src 'self' blob:",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "worker-src 'self' blob:",
].join("; ");

const BASE_HEADERS = [
  { key: "content-security-policy", value: CONTENT_SECURITY_POLICY },
  { key: "x-content-type-options", value: "nosniff" },
  { key: "x-frame-options", value: "DENY" },
  { key: "referrer-policy", value: "strict-origin-when-cross-origin" },
  // The composer uses the microphone for speech-to-text; nothing else is used.
  {
    key: "permissions-policy",
    value: "camera=(), microphone=(self), geolocation=(), payment=(), usb=(), interest-cohort=()",
  },
  { key: "cross-origin-opener-policy", value: "same-origin-allow-popups" },
  { key: "x-permitted-cross-domain-policies", value: "none" },
  { key: "x-dns-prefetch-control", value: "off" },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Standalone server output for the Docker image (root docker-compose.yml).
  output: "standalone",
  // `next dev` rewrites the build dir — if a production server is serving the
  // same .next it gets clobbered mid-run (fonts/CSS silently vanish). Point
  // dev elsewhere via NEXT_DIST_DIR=.next-dev when both must coexist.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  // Mermaid is lazy-loaded only when a ```mermaid block appears (audit-grade
  // bundle discipline: ~500KB never ships to users who don't hit diagrams).
  experimental: { optimizePackageImports: ["lucide-react", "framer-motion"] },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendOrigin}/api/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        // HSTS is only meaningful (and only safe) over HTTPS; sending it from a
        // dev server would pin localhost to https in the browser.
        source: "/:path*",
        headers: [
          ...BASE_HEADERS,
          ...(process.env.NODE_ENV === "production"
            ? [{ key: "strict-transport-security", value: "max-age=63072000; includeSubDomains" }]
            : []),
        ],
      },
    ];
  },
};

export default nextConfig;
