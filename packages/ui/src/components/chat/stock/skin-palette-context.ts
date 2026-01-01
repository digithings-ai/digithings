"use client";

import { createContext, useContext } from "react";
import type { SkinSlashPalette } from "./skin-slash-palette";

/** Set by `SkinPaletteBridge` when the host wired the product palette. */
export const SkinPaletteContext = createContext<SkinSlashPalette | null>(null);

/**
 * The shared palette, when the host wired one. A skin that mounts its own
 * `Unstable_TriggerPopoverRoot` reads this to drop that root (a nested root
 * shadows the shared one) and leave the `/` menu to the bridge.
 */
export function useSkinPaletteOptional(): SkinSlashPalette | null {
  return useContext(SkinPaletteContext);
}
