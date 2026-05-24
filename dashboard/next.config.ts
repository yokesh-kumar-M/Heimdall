import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow dev tooling (browsers, the chrome-devtools MCP, etc.) to hit the
  // dev server via 127.0.0.1 in addition to the default `localhost`. Next.js
  // 16 blocks cross-origin POST/Server Actions otherwise.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  // Trim the production Docker image — Next emits a self-contained server.js
  // and just the deps it actually uses, so the final stage doesn't need
  // node_modules.
  output: "standalone",
};

export default nextConfig;
