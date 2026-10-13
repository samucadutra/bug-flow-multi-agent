import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Strict mode runs effects twice in development, which would duplicate the API requests
  // that the stand-in records and that the browser tests count.
  reactStrictMode: false,
};

export default nextConfig;
