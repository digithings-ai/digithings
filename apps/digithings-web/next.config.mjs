import createMDX from "@next/mdx";

import { fileURLToPath } from "node:url";

// MDX plugins are named by MODULE PATH, not passed as functions. `next dev`
// runs Turbopack, which hands loader options across a process boundary and
// rejects functions ("does not have serializable options"); that failure is why
// chapters did not render under `next dev`. Strings work for both Turbopack
// (dev) and webpack (`next build --webpack`).
const local = (p) => fileURLToPath(new URL(p, import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  // The book (DIG-2821) is MDX under content/book, compiled by @next/mdx and
  // imported dynamically by app/book/[slug]/page.tsx. `.md`/`.mdx` are NOT in
  // pageExtensions on purpose: adding them would turn every chapter file into a
  // route of its own, and the chapter page already owns the URL.

  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
  transpilePackages: ["@digithings/ui", "@digithings/hero-banner"],
  eslint: { ignoreDuringBuilds: true },
  // Dev preview is often opened at 127.0.0.1 while `next dev` advertises localhost.
  // Next.js 16 blocks cross-origin HMR (and client hydration) unless allowlisted.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  // Cloudflare Pages serves dist/openwiki/index.html for /openwiki/. `next dev`
  // does not directory-index public/, so the Wiki nav 404s locally without this.
  // Static export ignores rewrites (Cloudflare still serves the directory index).
  async rewrites() {
    return [
      { source: "/openwiki/", destination: "/openwiki/index.html" },
      // The market-data Worker allows digithings.ai, not a local preview.
      // Dev-only: .env.local points the band here so the benchmark leg is the
      // same series production draws. Static export ignores this rewrite.
      { source: "/market-data/:path*", destination: "https://graph.digithings.ai/:path*" },
      // The house-book API allows digithings.ai, not a local preview.
      // Dev-only same-origin proxy. Static export ignores this rewrite.
      {
        source: "/dashboard-api/:path*",
        destination: "https://graph.digithings.ai/dashboard-api/:path*",
      },
    ];
  },
};

// `pageExtensions` left alone on purpose — see above.
const withMDX = createMDX({
  // Any .md/.mdx file, including the ones outside app/, so the dynamic import
  // in the chapter page goes through the same loader.
  extension: /\.mdx?$/,
  options: {
    // Heading ids, so the static HTML already carries the anchors the table of
    // contents links to and the printed book resolves its page numbers from.
    // The plugin's slug rules are pinned to lib/book/headings.ts by
    // rehypeBookIds.test.ts.
    rehypePlugins: [local("./lib/book/rehypeBookIds.mjs")],
    // Mermaid fences become `<img>` pointing at the static SVG, so the chapter
    // never asks a browser to run mermaid and the printed page loads the same
    // file the page does. See lib/book/remarkBookDiagrams.mjs.
    // `remark-frontmatter` FIRST: a chapter's `---` header was reaching the
    // page as a paragraph reading "title: … order: 2 summary: >- …". Parsing it
    // as YAML makes it a `yaml` node, which renders nothing. The book reads the
    // same fields itself (lib/book/frontmatter.ts), so this plugin only has to
    // stop the header being printed.
    // `remark-gfm`: MDX is CommonMark only, so without it every pipe table in a
    // chapter rendered as a paragraph of `| --- | --- |` — the "rows of
    // horizontal bars" in the first review. Tables are GFM; so is the book.
    remarkPlugins: ["remark-frontmatter", "remark-gfm", local("./lib/book/remarkBookDiagrams.mjs")],
  },
});

export default withMDX(nextConfig);
