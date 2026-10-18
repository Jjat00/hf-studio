import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // La imagen Docker (`hf-studio cloud`) arranca la UI con el servidor autónomo de Next.
  output: process.env.HF_STUDIO_STANDALONE ? "standalone" : undefined,
};

export default nextConfig;
