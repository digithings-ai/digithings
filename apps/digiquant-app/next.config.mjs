/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: { agentUpgrade: "security" },
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
};

export default nextConfig;
