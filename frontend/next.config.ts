import type { NextConfig } from "next";

const backendOrigin = (
  process.env.VEDNIX_BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : "https://vednix.onrender.com")
).trim().replace(/\/$/, "");

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
};

export default nextConfig;
