/**
 * ChatWidgetFrame — the framed-embed grammar promoted from the chatbot
 * reference family (#1418): the container for any object the assistant drops
 * into a turn. Two variants:
 *   - "card" (default): a surface card — optional head row (micro-caps accent
 *     eyebrow, mono title, right-side badge), unpadded body (children carry
 *     their own padding, so grids can run edge-to-edge), and an optional
 *     bordered actions footer. The result cards and approval gates.
 *   - "embed": a bare hairline media frame (8px radius, overflow clipped) for
 *     inline charts/graphs — the frame is promoted, the chart/graph internals
 *     stay with the consumer.
 * Server component — no state, no effects. Action buttons come from
 * ChatWidgetButton (primary / ghost / danger tones); their transitions and
 * color-mix hovers live in styles/chat-widgets.css (import it once app-wide;
 * see the wiring note there). digichat-ui's ChatActivities `tool_result` /
 * status cards converge on this frame.
 */
import type { ComponentPropsWithoutRef, ReactNode } from "react";

export type ChatWidgetFrameVariant = "card" | "embed";

export type ChatWidgetFrameProps = {
  /** Micro-caps accent line above the title, e.g. `backtest complete`. */
  eyebrow?: string;
  /** Mono head title, e.g. `trend_xsec · ETH-USD · 8y`. */
  title?: ReactNode;
  /** Right side of the head row — a status pill, an icon. */
  badge?: ReactNode;
  /** Footer action row (compose ChatWidgetButton here). Card variant only. */
  actions?: ReactNode;
  variant?: ChatWidgetFrameVariant;
  /** Unpadded body — children own their padding. */
  children?: ReactNode;
  className?: string;
  "aria-label"?: string;
};

export function ChatWidgetFrame({
  eyebrow,
  title,
  badge,
  actions,
  variant = "card",
  children,
  className,
  "aria-label": ariaLabel,
}: ChatWidgetFrameProps) {
  const frame =
    variant === "embed"
      ? "overflow-hidden rounded-[8px] border border-hair"
      : "overflow-hidden rounded-[12px] border border-hair bg-surface";
  const hasHead = Boolean(eyebrow || title || badge);

  return (
    <article className={`${frame}${className ? ` ${className}` : ""}`} aria-label={ariaLabel}>
      {hasHead ? (
        <header className="flex items-start justify-between gap-[1rem] border-b border-hair px-[1rem] py-[0.85rem]">
          <div>
            {eyebrow ? (
              <p className="m-0 mb-[0.2rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-accent">
                {eyebrow}
              </p>
            ) : null}
            {title ? <h4 className="m-0 font-mono text-[0.86rem] text-ink">{title}</h4> : null}
          </div>
          {badge ? <span className="shrink-0">{badge}</span> : null}
        </header>
      ) : null}
      {children}
      {actions ? (
        <footer className="flex gap-[0.6rem] border-t border-hair px-[1rem] py-[0.8rem]">
          {actions}
        </footer>
      ) : null}
    </article>
  );
}

export type ChatWidgetButtonTone = "primary" | "ghost" | "danger";

export type ChatWidgetButtonProps = ComponentPropsWithoutRef<"button"> & {
  /** primary = accent fill, ghost = hairline, danger = down-toned hairline. */
  tone?: ChatWidgetButtonTone;
};

const TONES: Record<ChatWidgetButtonTone, string> = {
  primary: "cw-btn--primary border-transparent bg-accent",
  ghost: "cw-btn--ghost border-hair bg-transparent text-ink",
  danger: "cw-btn--danger bg-transparent text-down",
};

export function ChatWidgetButton({
  tone = "ghost",
  className,
  type,
  ...rest
}: ChatWidgetButtonProps) {
  return (
    <button
      type={type ?? "button"}
      className={`cw-btn cursor-pointer rounded-full border px-[1rem] py-[0.5rem] font-mono text-[0.72rem] ${TONES[tone]}${
        className ? ` ${className}` : ""
      }`}
      {...rest}
    />
  );
}
