/**
 * Brand: the plain `digiquant` wordmark exactly as digiquant.io's header renders it
 * (Geist Mono, 1.05rem, weight 400, no mark on desktop — the `d` + cursor mark is
 * only the narrow-screen fallback there). One tone, currentColor.
 */
export function Logo() {
  return (
    <span className="logo">
      <span className="logo-word">digiquant</span>
    </span>
  );
}
