"use client";
/**
 * ChatToolCall — the collapsible tool-call block promoted from the chatbot
 * reference family (#1418): one mono line — tool(args) · status mark ·
 * timing — that folds its output away, the Claude Code / opencode chain
 * pattern. The tool name takes the surface accent; ok/error wear the
 * money-adjacent up/down reads; a running call breathes its mark. Sits on the
 * terminal palette (term-* tokens), so it expects a term-bg transcript around
 * it. Uncontrolled by default (`defaultOpen`) or controlled via
 * `open`/`onOpenChange`. Output arrives as `lines` (string, or
 * `{ text, tone }` for up/down reads) and/or arbitrary `children` rendered
 * after them — enough surface for digichat-ui's ChatActivities to rebuild its
 * tool_call / tool_result / trace kinds on this primitive. A call with no
 * body renders its head as a plain row (no button). The left rail, color-mix
 * borders, and the running pulse live in styles/chat-widgets.css (import it
 * once app-wide; see the wiring note there). Click the head to expand —
 * a caret glyph plus `aria-expanded` carry the disclosure state.
 */
import { useEffect, useRef, useState, type ReactNode } from "react";

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
  error: { glyph: "✕", cls: "text-danger" },
};

const HEAD_CLS =
  "tc-head flex w-full items-center gap-[0.5rem] border-0 bg-transparent px-0 py-[0.2rem] text-left font-mono text-[0.78rem] text-term-ink";

function HeadContent({
  name,
  args,
  status,
  duration,
  showCaret,
  isOpen,
}: {
  name: string;
  args?: string;
  status: ChatToolCallStatus;
  duration?: string;
  showCaret: boolean;
  isOpen: boolean;
}) {
  const mark = MARKS[status];
  return (
    <>
      {showCaret ? (
        <span className={`tc-caret${isOpen ? " open" : ""}`} aria-hidden="true" />
      ) : null}
      {/* `shrink-0 whitespace-nowrap`: the name is the one thing on this line
          that must never break. Without them a flex row under width pressure
          (a narrow embed, a long args string) shrinks every item somewhat
          evenly, and a shrunk name span with the default `white-space: normal`
          wraps mid-word — "file_search" split "file_ / searc / h" across three
          lines, observed live. `args` carries `min-w-0 flex-1 truncate` so it
          is the one thing that absorbs the missing space, ellipsised, never
          the name. */}
      <span className="shrink-0 whitespace-nowrap text-accent">{name}</span>
      {args ? (
        <span className="min-w-0 flex-1 truncate text-term-mute">({args})</span>
      ) : null}
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
  // Tracks a real user toggle. Streaming rows keep a stable React key across
  // tool_call → tool_result (see digichat-ui activity-view identityKey), so
  // `defaultOpen` can flip true on settle without a remount — and useState
  // only reads its initial argument. Adopt the new default until the reader
  // has touched the control; after that, their choice wins.
  const touched = useRef(false);
  const isOpen = open !== undefined ? open : ownOpen;
  const hasBody = Boolean(lines?.length) || (children !== undefined && children !== null);

  useEffect(() => {
    if (open !== undefined) return;
    if (touched.current) return;
    if (defaultOpen) setOwnOpen(true);
  }, [defaultOpen, open]);

  const toggle = () => {
    const next = !isOpen;
    touched.current = true;
    if (open === undefined) setOwnOpen(next);
    onOpenChange?.(next);
  };

  return (
    <div
      className={`tc${status === "error" ? " tc--err" : ""}${
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
          <HeadContent
            name={name}
            args={args}
            status={status}
            duration={duration}
            showCaret
            isOpen={isOpen}
          />
        </button>
      ) : (
        <div className={HEAD_CLS}>
          <HeadContent
            name={name}
            args={args}
            status={status}
            duration={duration}
            showCaret={false}
            isOpen={false}
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
