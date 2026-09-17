import { cn } from "../lib/utils";

export type SpinnerProps = {
  /** Extra utilities (size overrides, margins, colours) merged after the base. */
  className?: string;
};

/**
 * Spinner — the canonical inline loading glyph. The wave-3 shared replacement
 * for the hand-rolled `<span className="size-[11px] … animate-spin
 * rounded-full border-2 border-current/30 border-t-current" />` idiom that had
 * been copied into three reference specimens (task-1b review, Minor 3).
 *
 * `currentColor`-based, so it inherits the button/label tone; motion-reduce
 * disables the rotation. Import from `@digithings/web`.
 */
export function Spinner({ className }: SpinnerProps) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "size-[11px] shrink-0 animate-spin rounded-full border-2 border-current/30 border-t-current motion-reduce:animate-none",
        className
      )}
    />
  );
}
