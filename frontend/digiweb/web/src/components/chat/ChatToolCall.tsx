"use client";
/**
 * ChatToolCall — the collapsible tool-call block promoted from the chatbot
 * reference family (#1418): one mono line — caret · tool(args) · status mark ·
 * timing — that folds its output away, the Claude Code / opencode chain
 * pattern. The tool name takes the surface accent; ok/error wear the
 * money-adjacent up/down reads; a running call breathes its mark. Sits on the
 * terminal palette (term-* tokens), so it expects a term-bg transcript around
 * it. Uncontrolled by default (`defaultOpen`) or controlled via
 * `open`/`onOpenChange`. Output arrives as `lines` (string, or
 * `{ text, tone }` for up/down reads) and/or arbitrary `children` rendered
 * after them — enough surface for digichat-ui's ChatActivities to rebuild its
 * tool_call / tool_result / trace kinds on this primitive. A call with no
 * body renders its head as a plain row (no button, caret hidden). Caret art,
 * the aria-expanded rotate, color-mix rails, and the running pulse live in
 * styles/chat-widgets.css (import it once app-wide; see the wiring note
 * there).
 */
import { useState, type ReactNode } from "react";

export type ChatToolCallStatus = "running" | "ok" | "error";

export type ChatToolCallLine = string | { text: string; tone?: "up" | "down" };

export type ChatToolCallProps = {
  /** Tool name, e.g. `digiquant.backtest` — rendered in the accent. */
  name: string;
  /** Argument summary, rendered `(args)` and truncated when long. */
  args?: string;
  /** ok → up ✓, error → down ✕, running → pulsing ellipsis. */
  status?: ChatToolCallStatus;
  /** Right-aligned mono timing, e.g. `412ms`. */
  duration?: string;
  /** Output lines; a tone gives a line the up/down read. */
  lines?: ChatToolCallLine[];
  /** Custom output body (hit lists, rich results) rendered after `lines`. */
  children?: ReactNode;
  defaultOpen?: boolean;
  /** Controlled open state; omit to let the block own it. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
};

const MARKS: Record<ChatToolCallStatus, { glyph: string; cls: string }> = {
  running: { glyph: "…", cls: "tc-run text-term-mute" },
  ok: { glyph: "✓", cls: "text-up" },
  error: { glyph: "✕", cls: "text-down" },
};

const HEAD_CLS =
  "tc-head flex w-full items-center gap-[0.5rem] border-0 bg-transparent px-0 py-[0.2rem] text-left font-mono text-[0.78rem] text-term-ink";

function HeadContent({
  name,
  args,
  status,
  duration,
  expandable,
}: {
  name: string;
  args?: string;
  status: ChatToolCallStatus;
  duration?: string;
  expandable: boolean;
}) {
  const mark = MARKS[status];
  return (
    <>
      <span className={`tc-caret${expandable ? "" : " invisible"}`} aria-hidden="true" />
      <span className="text-accent">{name}</span>
      {args ? <span className="min-w-0 truncate text-term-mute">({args})</span> : null}
      <span className={`ml-auto shrink-0 ${mark.cls}`}>{mark.glyph}</span>
      {duration ? (
        <span className="min-w-[3rem] shrink-0 text-right text-[0.7rem] text-term-mute">
          {duration}
        </span>
      ) : null}
    </>
  );
}

export function ChatToolCall({
  name,
  args,
  status = "ok",
  duration,
  lines,
  children,
  defaultOpen = false,
  open,
  onOpenChange,
  className,
}: ChatToolCallProps) {
  const [ownOpen, setOwnOpen] = useState(defaultOpen);
  const isOpen = open !== undefined ? open : ownOpen;
  const hasBody = Boolean(lines?.length) || (children !== undefined && children !== null);

  const toggle = () => {
    const next = !isOpen;
    if (open === undefined) setOwnOpen(next);
    onOpenChange?.(next);
  };

  return (
    <div
      className={`tc pl-[0.7rem]${status === "error" ? " tc--err" : ""}${
        className ? ` ${className}` : ""
      }`}
    >
      {hasBody ? (
        <button
          type="button"
          className={`${HEAD_CLS} cursor-pointer`}
          aria-expanded={isOpen}
          onClick={toggle}
        >
          <HeadContent name={name} args={args} status={status} duration={duration} expandable />
        </button>
      ) : (
        <div className={HEAD_CLS}>
          <HeadContent
            name={name}
            args={args}
            status={status}
            duration={duration}
            expandable={false}
          />
        </div>
      )}
      {hasBody && isOpen ? (
        <div className="pb-[0.4rem] pl-[0.75rem] pt-[0.15rem]">
          {lines?.map((l) => {
            const line = typeof l === "string" ? { text: l, tone: undefined } : l;
            const tone =
              line.tone === "down"
                ? "text-down"
                : line.tone === "up"
                  ? "text-up"
                  : "text-term-mute";
            return (
              <p
                key={line.text}
                className={`my-[0.12rem] font-mono text-[0.74rem] leading-[1.5] ${tone}`}
              >
                {line.text}
              </p>
            );
          })}
          {children}
        </div>
      ) : null}
    </div>
  );
}
