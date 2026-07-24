import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Standalone server output for the Docker image (root docker-compose.yml).
  output: "standalone",
  // Mermaid is lazy-loaded only when a ```mermaid block appears (audit-grade
  // bundle discipline: ~500KB never ships to users who don't hit diagrams).
  experimental: { optimizePackageImports: ["lucide-react", "framer-motion"] },
};

export default nextConfig;
