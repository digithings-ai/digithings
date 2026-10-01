import type { ReactNode } from "react";
import { Reveal } from "@digithings/ui";
import { Badge } from "@digithings/ui/ui";
import { BANDS, type BandId } from "../_bands/registry";

/** One band on the hairline frame: id anchor, `NN/07 ~/digiquant/<id>` label,
 *  one idea, one interactive piece. `status` is the honesty badge.
 *
 *  Bands must not all look alike, so the shell has a few shapes:
 *  - `stack`  header above the piece (default)
 *  - `split`  header left, piece right (`flip` swaps them)
 *  - `center` centred header over the piece
 *  `tint` paints a full-width surface behind the band. */
type Layout = "stack" | "split" | "center";

export function Band({
  id,
  title,
  takeaway,
  status = "placeholder",
  layout = "stack",
  flip = false,
  tint = false,
  children,
}: {
  id: BandId;
  title: string;
  takeaway: string;
  status?: string;
  layout?: Layout;
  flip?: boolean;
  tint?: boolean;
  children?: ReactNode;
}) {
  const index = BANDS.findIndex((b) => b.id === id);
  const n = String(index + 1).padStart(2, "0");
  const centered = layout === "center";
  const header = (
    <div className={centered ? "mx-auto flex max-w-[44rem] flex-col items-center text-center" : "flex flex-col"}>
      <div className="mb-4 flex items-center gap-3 font-mono text-[0.68rem] text-ink-mute">
        <span>
          {n}/{String(BANDS.length).padStart(2, "0")} ~/digiquant/{id}
        </span>
        <Badge variant="neutral">{status}</Badge>
      </div>
      <h2 id={`${id}-h`} className="m-0 text-[clamp(1.5rem,3.2vw,2.25rem)] font-normal leading-tight text-ink">
        {title}
      </h2>
      <p className="mt-3 max-w-[46ch] text-ink-soft">{takeaway}</p>
    </div>
  );
  const piece = <div className={layout === "split" ? "min-w-0" : "mt-8 min-w-0"}>{children}</div>;
  return (
    <section
      id={id}
      aria-labelledby={`${id}-h`}
      className={`relative z-10 border-b border-hair ${tint ? "bg-surface" : ""}`}
    >
      <Reveal className="mx-auto w-full max-w-[var(--frame-w)] px-[var(--page-pad)] py-[var(--page-step)]">
        {layout === "split" ? (
          <div className="grid items-center gap-[2.4rem] min-[960px]:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
            <div className={flip ? "min-[960px]:order-2" : undefined}>{header}</div>
            {piece}
          </div>
        ) : (
          <>
            {header}
            {piece}
          </>
        )}
      </Reveal>
    </section>
  );
}

/** Dashed placeholder box; `height` hints at the size of the piece it stands in for. */
export function Slot({ label, height = "12rem" }: { label: string; height?: string }) {
  return (
    <div
      role="img"
      aria-label={label}
      style={{ minHeight: height }}
      className="grid w-full place-items-center border border-dashed border-hair bg-transparent p-4 text-center text-[0.72rem] text-ink-mute"
    >
      {label}
    </div>
  );
}
