/** Wide-layout sidebar widths. The phone drawer does not use these steps. */
export const RAIL_WIDTHS = [160, 200, 248, 320] as const;

export const RAIL_WIDTH_DEFAULT = 200;

export function stepRailWidth(current: number, dir: -1 | 1): number {
  const widths: readonly number[] = RAIL_WIDTHS;
  const index = widths.indexOf(current);
  const at = index >= 0 ? index : widths.indexOf(RAIL_WIDTH_DEFAULT);
  const next = Math.min(widths.length - 1, Math.max(0, at + dir));
  return widths[next] ?? RAIL_WIDTH_DEFAULT;
}
