/**
 * Class joiners for the controls family. Deliberately NOT tailwind-merge:
 * base-vs-call-site utility conflicts are resolved by layering instead —
 * every default a call site may override lives in `@layer components` in
 * styles/controls-overlay.css, where the app's utilities layer wins.
 */
export const cx = (...parts: Array<string | false | null | undefined>): string =>
  parts.filter(Boolean).join(" ");

/**
 * Composes a base class string with a Base UI `className` prop, which may be
 * a plain string or a `(state) => string` resolver — the function form is
 * preserved so state-driven classes keep working through the wrappers.
 */
export function cxBase<State>(
  base: string,
  className?: string | ((state: State) => string | undefined),
): string | ((state: State) => string) {
  if (typeof className === "function") {
    return (state: State) => cx(base, className(state));
  }
  return cx(base, className);
}
