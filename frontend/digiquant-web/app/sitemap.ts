import type { MetadataRoute } from "next";

export const dynamic = "force-static";

const BASE = "https://digiquant.io";

const STATIC_ROUTES = [
  "/",
  "/strategies",
  "/strategies/btc_slapper",
  "/strategies/eth_slapper",
  "/strategies/sol_slapper",
  "/strategies/btc_sdca",
  "/subsystems/research",
  "/subsystems/portfolio",
  "/subsystems/execution",
  "/changelog",
  "/contact",
];

export default function sitemap(): MetadataRoute.Sitemap {
  return STATIC_ROUTES.map((route) => ({
    url: `${BASE}${route}`,
    lastModified: new Date(),
  }));
}
