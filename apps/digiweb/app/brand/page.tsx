import type { Metadata } from "next";
import Link from "next/link";
import { BrandStudio } from "@/components/brand/studio/brand-studio";
import { ModuleBanners } from "@/components/brand/studio/module-banners";
import "./studio.css";

export const metadata: Metadata = {
  title: "brand studio — digiweb",
  description: "Compose and export the digithings logo and hero wordmark.",
};

/**
 * Brand studio — the working brand surface.
 *
 * Local design-reference only (`npm run dev --workspace @digithings/digiweb`).
 * It replaces the old upload-kit page: compose, preview and export here; the
 * generated files stay canonical in `packages/brand/`.
 */
export default function BrandStudioPage() {
  return (
    <main className="reference-page brand-studio-page">
      <header className="hero">
        <p className="kicker">{"// brand studio"}</p>
        <h1>
          Compose the <em>mark.</em>
        </h1>
        <p>
          The working brand kit: the three-column Jenga logo, the 4×4 hero wordmark, the
          embedding field, and every upload preset. Compose a header, card, story or icon,
          then export a still PNG or a self-contained SVG. The wordmark carries headers, web
          and docs; the logo carries icons and favicons — one or the other, never both.
        </p>
        <p className="bs-hero-links">
          <Link href="/components">The kit index →</Link>
        </p>
      </header>

      <BrandStudio />
      <ModuleBanners />
    </main>
  );
}
