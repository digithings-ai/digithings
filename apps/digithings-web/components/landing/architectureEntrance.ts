/**
 * Where the architecture drawing should be when the band is measured.
 *
 * The build hides every box until it runs. That hide is for a reader scrolling
 * down into the band. A refresh, a back navigation, or a scroll back up can
 * put a later diagram on screen while the first one is still above the
 * viewport — the hide would leave that diagram blank. If any of the band is
 * already on screen, or the reader has already passed it, the drawing is
 * finished. `wait` is only for a band still entirely below the viewport.
 */
export function architectureEntrance(
  rect: { top: number; bottom: number; height: number },
  viewportHeight: number,
): "wait" | "done" {
  if (rect.height <= 0 || viewportHeight <= 0) return "wait";
  if (rect.top < viewportHeight) return "done";
  return "wait";
}
