/** Turn mutation modes for POST /api/chat (`X-Digi-Turn-Mode`, #3475). */

export const DIGI_TURN_MODES = ["send", "regenerate", "edit_last_user"] as const;

export type DigiTurnMode = (typeof DIGI_TURN_MODES)[number];

export function parseDigiTurnMode(raw: string | null | undefined): DigiTurnMode | "invalid" {
  const value = (raw ?? "send").trim().toLowerCase();
  if (!value) return "send";
  if ((DIGI_TURN_MODES as readonly string[]).includes(value)) {
    return value as DigiTurnMode;
  }
  return "invalid";
}

export function isMutatingTurnMode(mode: DigiTurnMode): boolean {
  return mode === "regenerate" || mode === "edit_last_user";
}
