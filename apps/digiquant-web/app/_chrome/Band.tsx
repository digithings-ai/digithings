import type { ReactNode } from "react";
import { Reveal } from "@digithings/ui";
import { Badge } from "@digithings/ui/ui";
import { BANDS, type BandId } from "../_bands/registry";

const pad2 = (n: number) => String(n).padStart(2, "0");

/** One band on the hairline frame, same shell as digithings.ai: a left-aligned
 *  `NN / label` eyebrow, an Inter title, a one-line lede, then the piece on the
 *  same column grid. `status` is the honesty badge. `tint` paints a full-width
 *  surface behind the band. */
export function Band({
  id,
  title,
  takeaway,
  status = "placeholder",
  tint = false,
  children,
}: {
  id: BandId;
  title: string;
  takeaway: string;
  status?: string;
  tint?: boolean;
  children?: ReactNode;
}) {
  const index = BANDS.findIndex((b) => b.id === id);
  const label = BANDS[index]?.label ?? id;
  return (
    <section
      id={id}
      aria-labelledby={`${id}-h`}
      className={`relative z-10 border-b border-hair ${tint ? "bg-surface" : ""}`}
    >
      <Reveal className="mx-auto flex w-full max-w-[var(--frame-w)] flex-col gap-[2rem] px-[var(--page-pad)] py-[var(--page-step)]">
        <header className="flex flex-col gap-[0.7rem]">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <p className="section-eyebrow m-0">
              <span aria-hidden="true" className="section-eyebrow__tick" />
              {pad2(index + 1)} / {label}
            </p>
            <Badge variant="neutral">{status}</Badge>
          </div>
          <h2
            id={`${id}-h`}
            className="m-0 max-w-[28ch] font-display text-[clamp(1.5rem,3.2vw,2.25rem)] font-medium leading-[1.2] tracking-[-0.025em] text-balance text-ink"
          >
            {title}
          </h2>
          <p className="m-0 max-w-[var(--measure-prose)] text-[0.9375rem] leading-[1.65] text-ink-soft">{takeaway}</p>
        </header>
        <div className="min-w-0">{children}</div>
      </Reveal>
    </section>
  );
}
