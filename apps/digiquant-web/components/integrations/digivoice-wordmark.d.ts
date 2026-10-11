export const BUILD_MS: number;
export const LIT_SHADE: { step: number; rgb: number; cube: number };
export const REST_SHADE: { step: number; rgb: number; cube: number };

export function wordmarkLines(
  word?: string,
  options?: {
    cols?: number;
    rows?: number;
    tMs?: number;
    truecolor?: boolean;
    scale?: number;
  },
): {
  lines: {
    ch: string;
    color: { rgb?: number; cube?: number } | null;
    bg?: { rgb?: number; cube?: number };
  }[][];
  gap: number;
  rows: number;
  cubes: { x: number; y: number; bright: boolean }[];
  scale: number;
};
