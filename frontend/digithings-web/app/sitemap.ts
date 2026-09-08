import type { MetadataRoute } from "next";
import { OPENAPI_SERVICE_IDS } from "@/lib/openapiCatalog";

export const dynamic = "force-static";

const BASE = "https://digithings.ai";

const STATIC_ROUTES = [
  "/",
  "/about",
  "/services",
  "/team",
  "/security",
  "/quality",
  "/changelog",
  "/legal/privacy",
  "/docs",
  "/docs/api",
];

export default function sitemap(): MetadataRoute.Sitemap {
  const apiRoutes = OPENAPI_SERVICE_IDS.map((id) => `/docs/api/${id}`);
  return [...STATIC_ROUTES, ...apiRoutes].map((route) => ({
    url: `${BASE}${route}`,
    lastModified: new Date(),
  }));
}
