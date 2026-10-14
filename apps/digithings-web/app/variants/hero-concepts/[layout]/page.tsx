import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DtFooter } from "@/components/DtFooter";
import { StandardNav } from "@/app/_variants/headers";
import { EmbeddingField } from "@/components/landing/concepts/EmbeddingField";
import { LAYOUTS } from "@/components/landing/concepts/layouts";
import { PixelWordmark } from "@/components/landing/PixelWordmark";

// DIG-3319 round 2: the embedding-space map in the real hero lockup. Exploration only, not wired into `/`.

export const dynamicParams = false;

export function generateStaticParams() {
  return LAYOUTS.map((l) => ({ layout: l.slug }));
}

type Props = { params: Promise<{ layout: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { layout } = await params;
  const info = LAYOUTS.find((l) => l.slug === layout);
  return {
    title: `hero concept · embedding map ${info?.name ?? ""} — exploration`,
    robots: { index: false, follow: false },
  };
}

export default async function HeroEmbeddingConcept({ params }: Props) {
  const { layout } = await params;
  const info = LAYOUTS.find((l) => l.slug === layout);
  if (!info) notFound();
  return (
    <>
      <StandardNav />
      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <section className="pixel-hero border-b border-hair">
          <EmbeddingField layout={info.slug} />
          <div className="relative z-10 mx-auto flex max-w-[64rem] flex-col items-center px-[var(--page-pad)] pb-[6rem] pt-[2.5rem] text-center sm:px-[2.5rem] sm:pb-[7rem]">
            <PixelWordmark />
            <h1 className="m-0 mt-[2rem] font-display text-[1.5rem] font-semibold leading-[1.25] tracking-[-0.02em] text-balance text-ink sm:text-[1.7rem]">
              AI infrastructure, in a glass box you own.
            </h1>
            <p className="m-0 mt-[0.75rem] max-w-[42rem] text-[0.9375rem] leading-[1.6] text-pretty text-ink-soft">
              Chat, research and quant modules on your own keys and hardware.
            </p>
            {/* Stand-in for the clone row + facts so the hero is as tall as the real one. */}
            <div aria-hidden="true" className="mt-[1.75rem] h-[3.2rem]" />
            <p className="m-0 mt-[1.4rem] font-mono text-[0.72rem] leading-[1.5] tracking-[0.02em] text-ink-mute">
              self-hosted / your own keys / no hosted tier
            </p>
          </div>
        </section>
        <div className="mx-auto max-w-[64rem] px-[var(--page-pad)] py-[2rem] font-mono text-[0.78rem] leading-[1.7] text-ink-mute sm:px-[2.5rem]">
          DIG-3319 · embedding map · {info.name} — {info.note}{" "}
          <Link href="/variants/hero-concepts" className="text-ink underline-offset-[3px] hover:underline">
            all layouts
          </Link>
        </div>
      </main>
      <DtFooter />
    </>
  );
}
