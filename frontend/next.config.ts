import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        // Proxy all /backend/* requests to the FastAPI server so the
        // frontend never has to hardcode a port or deal with CORS in
        // production. Change the destination for non-local deployments.
        source: "/backend/:path*",
        destination: "http://localhost:8000/:path*",
      },
    ];
  },
};

export default nextConfig;
