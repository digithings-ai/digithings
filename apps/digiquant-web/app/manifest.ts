import type { MetadataRoute } from "next";

export const dynamic = "force-static";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "digiquant",
    short_name: "digiquant",
    description: "Open-source research-to-execution infrastructure for quantitative investing.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#0A0E0C", // canon-allow: manifests cannot reference CSS tokens
    theme_color: "#0A0E0C", // canon-allow: manifests cannot reference CSS tokens
    icons: [
      {
        src: "/icons/digi-app-192.png",
        sizes: "192x192",
        type: "image/png",
      },
      {
        src: "/icons/digi-app-512.png",
        sizes: "512x512",
        type: "image/png",
      },
      {
        src: "/icons/digi-app-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}