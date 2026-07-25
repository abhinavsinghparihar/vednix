import type { NextConfig } from "next";

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
};

export default nextConfig;
