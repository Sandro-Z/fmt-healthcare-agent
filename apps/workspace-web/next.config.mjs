import { fileURLToPath } from "node:url";
import nextEnv from "@next/env";

// Load the repository environment for both `next build` and `next start`.
nextEnv.loadEnvConfig(fileURLToPath(new URL("../../", import.meta.url)));
const apiPort = process.env.WGS_API_PORT || "8503";
if (!/^\d{1,5}$/.test(apiPort) || Number(apiPort) < 1 || Number(apiPort) > 65535) {
  throw new Error("WGS_API_PORT must be a port between 1 and 65535");
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [{ source: "/backend/:path*", destination: `http://127.0.0.1:${apiPort}/:path*` }];
  },
};
export default nextConfig;
