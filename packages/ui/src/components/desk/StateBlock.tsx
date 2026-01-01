"use client";

import { Component, type ReactNode } from "react";
import { cn } from "../../lib/utils";
import { Spinner } from "../Spinner";

export type StateKind = "empty" | "loading" | "error" | "withheld";

export type StateBlockProps = {
  kind: StateKind;
  /** One line naming the state; defaults per kind. */
  title?: string;
  /** Why the state is showing — the route, the failure, the missing input.
   *  A withheld block without a reason is an unexplained blank. */
  reason?: string;
  /** Optional retry, rendered as a real button. Omit when the state is terminal. */
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
};

const MARKER: Record<StateKind, string> = {
  empty: "[empty]",
  loading: "[loading]",
  error: "[!]",
  withheld: "[withheld]",
};

const TITLE: Record<StateKind, string> = {
  empty: "Nothing here yet.",
  loading: "Loading.",
  error: "Could not load.",
  withheld: "Withheld.",
};

/**
 * StateBlock — one layout for the four states a data surface can be in.
 *
 * Loading is announced (`role="status"`, `aria-busy`) and its spinner stops under
 * reduced motion. An error is announced (`role="alert"`) and carries a `[!]`
 * marker, so its meaning survives someone who cannot see the danger colour.
 * Withheld is a refusal, not a failure: it says why the figure is not shown.
 */
export function StateBlock({
  kind,
  title,
  reason,
  onRetry,
  retryLabel = "retry",
  className,
}: StateBlockProps) {
  const role =
    kind === "error"
      ? "alert"
      : kind === "loading"
        ? "status"
        : kind === "withheld"
          ? "note"
          : undefined;
  return (
    <div
      data-state={kind}
      role={role}
      aria-busy={kind === "loading" || undefined}
      className={cn(
        "rounded-none border border-hair bg-surface px-3 py-3",
        kind === "error" && "border-l-danger",
        kind === "withheld" && "bg-surface-2",
        className,
      )}
    >
      <p className="flex items-baseline gap-2 font-mono text-[0.72rem]">
        {kind === "loading" ? <Spinner className="text-ink-mute" /> : null}
        <span
          aria-hidden="true"
          className={cn(
            "shrink-0 tracking-[0.06em]",
            kind === "error" ? "text-danger" : kind === "withheld" ? "text-ink" : "text-ink-mute",
          )}
        >
          {MARKER[kind]}
        </span>
        <span className={cn("text-[0.8125rem]", kind === "error" ? "text-danger" : "text-ink")}>
          {title ?? TITLE[kind]}
        </span>
      </p>
      {reason ? (
        <p className="mt-1 font-mono text-[0.72rem] leading-relaxed text-ink-soft">{reason}</p>
      ) : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className={cn(
            "mt-2 cursor-pointer rounded-none border border-hair px-2 py-1 font-mono text-[0.72rem] text-ink",
            "hover:border-hair-2 focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-accent",
          )}
        >
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
}

export type BlockBoundaryProps = {
  /** Names the source in the withheld reason — usually the API route. */
  label?: string;
  children: ReactNode;
};

type BoundaryState = { error: string | null };

/**
 * BlockBoundary — one block throwing on an odd payload must not take the page
 * down. It is replaced by a withheld state that names the source and the fault.
 * Remount it (`key`) when the payload changes to retry the block.
 */
export class BlockBoundary extends Component<BlockBoundaryProps, BoundaryState> {
  state: BoundaryState = { error: null };

  static getDerivedStateFromError(error: unknown): BoundaryState {
    return { error: error instanceof Error ? error.message : "render failed" };
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const source = this.props.label ? `${this.props.label}: ` : "";
    return <StateBlock kind="withheld" reason={`${source}unexpected response shape (${error})`} />;
  }
}
