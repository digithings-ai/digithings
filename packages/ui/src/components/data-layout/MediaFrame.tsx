import { cn } from "../../lib/utils";

/**
 * MediaFrame — a 16:9 framed artboard for a recording (video) or a still
 * (image), wearing the terminal chrome: a title row of bracketed micro-labels,
 * a REQUIRED honesty `badge`, the media, and a caption row. Props-driven and
 * honest: it shows only the `src` it is given.
 *
 * Without `src` it renders a designed placeholder, not a bare dashed box: the
 * title bar, a faint hairline grid, viewfinder corner ticks, a disabled play
 * glyph, and the caller's `placeholderLabel` ("recording to come") centred. A
 * `--:--:--` timecode stands in for a length it does not know.
 *
 * With `src` (kind "video", the default) it renders a native `<video>` with
 * controls, `muted`, `playsInline`, `preload="none"` and the optional `poster`;
 * it NEVER autoplays, so reduced motion and data-saver users get a still until
 * they press play. kind "image" renders an `<img>` (alt = caption) instead.
 *
 * Utilities-only server component: no CSS sheet, no keyframes, no state, no
 * motion. Tokens only (grid lines are `--hair`, wash is `--surface`).
 *
 * Wiring (in the consuming app):
 *   globals.css   @source "<path-to>/packages/ui/src/components/data-layout";
 */
export type MediaFrameProps = {
  /** Video (or image) URL. Omit for the placeholder state. */
  src?: string;
  /** Poster still for a video. */
  poster?: string;
  /** What the media shows — caption row, accessible name, image alt. */
  caption: string;
  /** Centred label of the placeholder state, e.g. "recording to come". */
  placeholderLabel: string;
  /** Title-row label, e.g. "dashboard walkthrough". */
  title: string;
  /** REQUIRED honesty badge in the chrome, e.g. "Placeholder · no recording yet". */
  badge: string;
  /** "video" (default) or "image". */
  kind?: "video" | "image";
  className?: string;
};

const CORNER = "pointer-events-none absolute size-3 border-ink-mute";

export function MediaFrame({
  src,
  poster,
  caption,
  placeholderLabel,
  title,
  badge,
  kind = "video",
  className,
}: MediaFrameProps) {
  return (
    <figure
      data-slot="media-frame"
      data-state={src ? "media" : "placeholder"}
      className={cn("m-0 min-w-0 border border-hair bg-surface font-mono", className)}
    >
      <div className="flex items-center gap-3 border-b border-hair px-3 py-2 text-[0.68rem] tracking-[0.04em] text-ink-mute">
        <span aria-hidden="true">{kind === "image" ? "[image]" : "[video]"}</span>
        <span className="min-w-0 flex-1 truncate text-ink-soft">{title}</span>
        <span className="shrink-0" aria-hidden="true">
          {src ? "[ready]" : "[empty]"}
        </span>
      </div>
      <div className="border-b border-hair px-3 py-1.5 text-[0.66rem] text-ink-soft" data-slot="media-frame-badge">
        {`◇ ${badge}`}
      </div>

      <div className="relative aspect-video w-full overflow-hidden bg-term-bg">
        {src ? (
          kind === "image" ? (
            // eslint-disable-next-line @next/next/no-img-element -- package part, no next/image dependency
            <img src={src} alt={caption} className="absolute inset-0 size-full object-cover" />
          ) : (
            <video
              className="absolute inset-0 size-full object-cover"
              src={src}
              poster={poster}
              controls
              muted
              playsInline
              preload="none"
              aria-label={caption}
            />
          )
        ) : (
          <div role="img" aria-label={`${placeholderLabel}: ${caption}`} className="absolute inset-0">
            <div
              aria-hidden="true"
              className="absolute inset-0 opacity-50 [background-image:linear-gradient(var(--hair)_1px,transparent_1px),linear-gradient(90deg,var(--hair)_1px,transparent_1px)] [background-size:2.5rem_2.5rem]"
            />
            <span aria-hidden="true" className={cn(CORNER, "start-3 top-3 border-s border-t")} />
            <span aria-hidden="true" className={cn(CORNER, "end-3 top-3 border-e border-t")} />
            <span aria-hidden="true" className={cn(CORNER, "bottom-3 start-3 border-b border-s")} />
            <span aria-hidden="true" className={cn(CORNER, "bottom-3 end-3 border-b border-e")} />
            <div aria-hidden="true" className="absolute inset-0 grid place-content-center justify-items-center gap-3">
              <button
                type="button"
                disabled
                tabIndex={-1}
                className="grid size-12 cursor-not-allowed place-items-center border border-hair bg-surface text-[1rem] text-ink-mute opacity-80"
              >
                ▶
              </button>
              <span className="border border-hair bg-surface px-3 py-1 text-[0.72rem] tracking-[0.06em] text-ink-soft">
                {`[ ${placeholderLabel} ]`}
              </span>
            </div>
            <span aria-hidden="true" className="absolute bottom-3 start-8 text-[0.62rem] tracking-[0.08em] text-ink-mute">
              --:--:--
            </span>
          </div>
        )}
      </div>

      <figcaption className="border-t border-hair px-3 py-2 text-[0.72rem] leading-[1.5] text-ink-soft">
        {caption}
      </figcaption>
    </figure>
  );
}
