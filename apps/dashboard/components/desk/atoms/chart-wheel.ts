/**
 * TODO(slice-b): Slice B's `DeskChart` owns this predicate. Vertical wheel
 * scrolls the pane column; horizontal wheel stays on the chart (plan lock 9).
 */
export function dominantVerticalWheel(deltaX: number, deltaY: number): boolean {
  return Math.abs(deltaY) > Math.abs(deltaX);
}
