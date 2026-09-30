import type { ReactNode } from "react";
import { Reveal } from "@digithings/ui";
import { Badge } from "@digithings/ui/ui";
import { BANDS, type BandId } from "../_bands/registry";

/** One band on the hairline frame: id anchor, `NN/07 ~/digiquant/<id>` label,
 *  one idea, one interactive piece. `status` is the honesty badge; Phase 0a
 *  bands are all `placeholder`. */
export function Band({
  id,
  title,
  takeaway,
  status = "placeholder",
  as: Heading = "h2",
  children,
}: {
  id: BandId;
  title: string;
  takeaway: string;
  status?: string;
  as?: "h1" | "h2";
  children?: ReactNode;
}) {
  const index = BANDS.findIndex((b) => b.id === id);
  const n = String(index + 1).padStart(2, "0");
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="relative z-10 border-b border-hair">
      <Reveal className="mx-auto w-full max-w-[var(--frame-w)] px-[var(--page-pad)] py-[var(--page-step)]">
        <div className="mb-4 flex items-center gap-3 font-mono text-[0.68rem] text-ink-mute">
          <span>
            {n}/{String(BANDS.length).padStart(2, "0")} ~/digiquant/{id}
          </span>
          <Badge variant="neutral">{status}</Badge>
        </div>
        <Heading id={`${id}-h`} className="m-0 text-[clamp(1.5rem,3.2vw,2.25rem)] font-normal leading-tight text-ink">
          {title}
        </Heading>
        <p className="mt-3 max-w-[60ch] text-ink-soft">{takeaway}</p>
        <div className="mt-6">{children}</div>
      </Reveal>
    </section>
  );
}

export function Slot({ label }: { label: string }) {
  return (
    <div
      role="img"
      aria-label={label}
      className="grid min-h-[12rem] w-full place-items-center border border-dashed border-hair text-[0.72rem] text-ink-mute"
    >
      {label}
    </div>
  );
}
