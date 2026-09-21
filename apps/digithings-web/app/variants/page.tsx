import type { Metadata } from "next";

import { CtaLink } from "@digithings/ui";
import { DtFooter } from "@/components/DtFooter";
import { StandardNav } from "@/app/_variants/headers";
import { BlockLabel, Doc, Specimen } from "@/app/_variants/parts";

// Exploration index — the seven home-page variants on one page, with the
// pick table. Not part of the site: noindex, absent from sitemap.ts, and only
// ever rendered by the dev server (the shipped export never contains it).

export const metadata: Metadata = {
  title: "home page variants — exploration",
  robots: { index: false, follow: false },
};

type Variant = {
  slug: string;
  name: string;
  width: string;
  bar: string;
  hero: string;
  stack: string;
  motion: string;
  note: string;
};

const VARIANTS: Variant[] = [
  {
    slug: "command-bar",
    name: "V1 · Command bar",
    width: "full-bleed",
    bar: "install strip + nav",
    hero: "2-up with a terminal",
    stack: "4-up bento",
    motion: "typed lines",
    note: "The install command is chrome, and the page opens beside the documented quick start.",
  },
  {
    slug: "specimen",
    name: "V2 · Specimen frames",
    width: "document 1180",
    bar: "standard nav",
    hero: "claim + lede",
    stack: "bento, tabbed 3 ways",
    motion: "hover",
    note: "The design reference's own rhythm: every block is a labelled frame. The stack can be re-cut by tier or by dependency.",
  },
  {
    slug: "instrument",
    name: "V3 · Instrument",
    width: "wide 1280",
    bar: "nav, copy-install action",
    hero: "split with figures",
    stack: "dense table",
    motion: "count-up",
    note: "Numbers above the fold and the stack as data. The request path carries no timings, because none are measured.",
  },
  {
    slug: "manifest",
    name: "V4 · Manifest",
    width: "72ch",
    bar: "flat mono links",
    hero: "claim + prose",
    stack: "ls-style listing",
    motion: "none",
    note: "No cards anywhere. The quietest, most utilitarian register — one line per module.",
  },
  {
    slug: "split",
    name: "V5 · Split",
    width: "full-bleed",
    bar: "floating (hover)",
    hero: "50/50 with an artefact",
    stack: "3-col bento",
    motion: "bar reveals",
    note: "A true half-and-half hero with the real compose table as the visual, under a bar that yields.",
  },
  {
    slug: "registry",
    name: "V6 · Registry",
    width: "document 1180",
    bar: "standard nav",
    hero: "none — bento leads",
    stack: "accordion",
    motion: "expand",
    note: "A stack browser rather than a pitch: the install lives in the hero cell, then every module opens in place.",
  },
  {
    slug: "receipt",
    name: "V7 · Receipt",
    width: "wide 1280",
    bar: "standard nav",
    hero: "one dense frame",
    stack: "3-up artefacts",
    motion: "none",
    note: "The whole pitch in a single frame, then the three source files side by side.",
  },
];

export default function VariantsIndex() {
  return (
    <>
      <StandardNav />
      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)] pb-[var(--page-step)]">
        <Doc className="pt-[var(--page-step)]">
          <BlockLabel>exploration · not shipped</BlockLabel>
          <h1 className="mt-[0.9rem] mb-0 font-mono text-[length:var(--type-page-title)] font-medium leading-[1.2] tracking-[-0.02em] text-ink">
            Seven ways to open the page.
          </h1>
          <p className="mt-[1.1rem] mb-0 max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
            The same real content — the claim, the install command, the eleven modules, the counted
            figures, the repository snapshot and three crops of real files — composed seven
            different ways. Nothing here is wired into <span className="text-ink">/</span>. Look at
            them, then name the pieces you want and I will assemble the real page from exactly
            those.
          </p>

          <div className="mt-[2rem] grid gap-[0.8rem]">
            {VARIANTS.map((v) => (
              <Specimen key={v.slug}>
                <div className="flex flex-wrap items-baseline justify-between gap-[0.8rem]">
                  <a href={`/variants/${v.slug}`} className="font-mono text-[0.95rem] text-ink underline-offset-[3px] hover:underline">
                    {v.name}
                  </a>
                  <span className="font-mono text-[var(--type-meta)] text-ink-mute">
                    {v.width} · {v.bar}
                  </span>
                </div>
                <p className="mt-[0.6rem] mb-0 max-w-[var(--measure-prose)] text-[0.92rem] leading-[1.7] text-ink-soft">
                  {v.note}
                </p>
              </Specimen>
            ))}
          </div>

          <div className="mt-[2.5rem]">
            <BlockLabel>the pick sheet</BlockLabel>
            <div className="mt-[1rem] overflow-x-auto border border-hair">
              <table className="w-full border-collapse text-left font-mono text-[0.78rem]">
                <thead>
                  <tr className="text-ink-mute">
                    <th className="border-b border-hair p-[0.6rem] font-normal uppercase tracking-[var(--tracking-meta)]">variant</th>
                    <th className="border-b border-hair p-[0.6rem] font-normal uppercase tracking-[var(--tracking-meta)]">width</th>
                    <th className="border-b border-hair p-[0.6rem] font-normal uppercase tracking-[var(--tracking-meta)]">top bar</th>
                    <th className="border-b border-hair p-[0.6rem] font-normal uppercase tracking-[var(--tracking-meta)]">hero</th>
                    <th className="border-b border-hair p-[0.6rem] font-normal uppercase tracking-[var(--tracking-meta)]">stack</th>
                    <th className="border-b border-hair p-[0.6rem] font-normal uppercase tracking-[var(--tracking-meta)]">motion</th>
                  </tr>
                </thead>
                <tbody>
                  {VARIANTS.map((v) => (
                    <tr key={v.slug} className="text-ink-soft">
                      <td className="border-b border-hair p-[0.6rem] text-ink">{v.name}</td>
                      <td className="border-b border-hair p-[0.6rem]">{v.width}</td>
                      <td className="border-b border-hair p-[0.6rem]">{v.bar}</td>
                      <td className="border-b border-hair p-[0.6rem]">{v.hero}</td>
                      <td className="border-b border-hair p-[0.6rem]">{v.stack}</td>
                      <td className="border-b border-hair p-[0.6rem]">{v.motion}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="mt-[1.6rem] flex flex-wrap items-center gap-[0.8rem]">
            <CtaLink href="/variants/command-bar">Start with V1</CtaLink>
            <CtaLink href="/" variant="ghost">
              Back to the current home page
            </CtaLink>
          </div>
        </Doc>
      </main>
      <DtFooter />
    </>
  );
}
