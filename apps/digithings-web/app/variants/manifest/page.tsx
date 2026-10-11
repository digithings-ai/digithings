import type { Metadata } from "next";

import { CtaLink, Mono } from "@digithings/ui";
import { MonoNav } from "@/app/_variants/headers";
import { Narrow } from "@/app/_variants/parts";
import { CLAIM, COUNTS, LEDE, SHIPPING_ROWS } from "@/app/_variants/content";
import { DtFooter } from "@/components/DtFooter";

// V4 · Manifest — editorial 72ch, no cards anywhere. The stack reads as a
// directory listing and the page is numbered 01/02/03. The deliberately quiet
// register. Exploration only.

export const metadata: Metadata = {
  title: "V4 · Manifest — variant",
  robots: { index: false, follow: false },
};

/** A numbered section rule: `01 ──────────────`. */
function Rule({ n, children }: { n: string; children: string }) {
  return (
    <div className="mt-[var(--page-step)] flex items-baseline gap-[0.9rem] border-t border-hair pt-[0.8rem]">
      <span className="font-mono text-[0.72rem] text-ink-mute">{n}</span>
      <span className="font-mono text-[0.72rem] uppercase tracking-[var(--tracking-meta)] text-ink-mute">
        {children}
      </span>
    </div>
  );
}

export default function VariantManifest() {
  return (
    <>
      <MonoNav />

      <main id="main" tabIndex={-1} className="pb-[var(--page-step)]">
        <Narrow className="pt-[var(--page-step)]">
          <h1 className="m-0 font-mono text-[length:var(--type-hero)] font-medium leading-[1.14] tracking-[-0.02em] text-ink">
            {CLAIM}
          </h1>
          <p className="mt-[1.2rem] mb-0 text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
            {LEDE}
          </p>
          <p className="mt-[1.1rem] mb-0 text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
            It is not a platform you move into. Every module is a service you can run alone, read
            the source of, and point at your own providers — and the whole thing is one{" "}
            <Mono>docker-compose.yml</Mono> you can read in a minute.
          </p>

          <Rule n="01">the modules</Rule>
          <ul className="mt-[1.2rem] m-0 grid list-none gap-0 p-0">
            {SHIPPING_ROWS.map((m) => (
              <li
                key={m.id}
                className="grid grid-cols-[9rem_1fr_4rem] items-baseline gap-[0.8rem] border-b border-hair py-[0.5rem] font-mono text-[0.8rem] max-[560px]:grid-cols-[7rem_1fr]"
              >
                <span className="text-ink">{m.name}/</span>
                <span className="text-ink-soft">{m.role}</span>
                <span className="text-right text-ink-mute max-[560px]:hidden">{m.tier}</span>
              </li>
            ))}
          </ul>
          <p className="mt-[0.9rem] mb-0 font-mono text-[0.72rem] text-ink-mute">
            {COUNTS.shipping} shipping. digistore/ and digilink/ are roadmap, so they are not listed.
          </p>

          <Rule n="02">what it costs you</Rule>
          <p className="mt-[1.1rem] mb-0 text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
            One machine, or a private network. {COUNTS.compose} services in the compose file,{" "}
            {COUNTS.composeDefault} of them up by default and the rest behind named profiles. Every
            one binds loopback until you decide otherwise, and the only bill is the model provider
            you choose — the stack itself stores {COUNTS.keysStored} keys.
          </p>

          <Rule n="03">what it is not</Rule>
          <p className="mt-[1.1rem] mb-0 text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
            It is not hosted, not managed, and not a live-trading system — the broker adapters raise{" "}
            <Mono>NotImplementedError</Mono> and a human co-sign hook guards those paths. Two of the
            eleven modules are roadmap. Where a claim here can be counted, it is counted and dated:{" "}
            {COUNTS.countedAt}, on a clean checkout.
          </p>

          <div className="mt-[2rem] flex flex-wrap items-center gap-[0.8rem]">
            <CtaLink href="/docs">Read the docs</CtaLink>
            <CtaLink href="/security" variant="ghost">
              Review security
            </CtaLink>
          </div>
        </Narrow>
      </main>

      <DtFooter />
    </>
  );
}
