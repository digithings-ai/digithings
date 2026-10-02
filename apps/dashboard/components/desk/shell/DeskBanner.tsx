import type { DeskBanner } from '@/lib/desk/spine';

export function DeskBanner({ banner }: { banner: DeskBanner }) {
  return (
    <section
      data-desk-banner={banner.badge}
      role="status"
      className="border border-hair bg-surface p-6"
    >
      <p className="font-mono text-[0.68rem] tracking-[0.08em] text-ink-mute uppercase">
        [{banner.badge}]
      </p>
      <h2 className="mt-2 font-sans text-lg text-ink">{banner.title}</h2>
      <p className="mt-2 max-w-prose text-sm leading-relaxed text-ink-soft">{banner.body}</p>
    </section>
  );
}
