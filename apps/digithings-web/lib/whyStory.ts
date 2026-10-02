/**
 * Beat math for the #why band (Refs #4429).
 *
 * One story per app: the rented architecture, then the same drawing moved
 * onto digithings one box at a time. The invoice's digi column stays blank
 * until the morph beats, and fills with the layers those beats have cut.
 */

import type { AppPreset } from "@/lib/appPresets";
import type { LayerId } from "@/lib/stackCatalog";

export interface StoryBeat {
  id: string;
  label: string;
  line: string;
  ids: string[];
  phase: "theirs" | "digi";
}

export function storyBeats(preset: AppPreset): StoryBeat[] {
  return [
    ...preset.leftSteps.map((step) => ({
      id: step.id,
      label: step.label,
      line: step.line,
      ids: step.ids,
      phase: "theirs" as const,
    })),
    ...preset.morphSteps.map((step) => ({
      id: step.id,
      label: step.label,
      line: step.line,
      ids: step.ids,
      phase: "digi" as const,
    })),
  ];
}

/** Index into `morphSteps`, or -1 while the rented walk is still on screen. */
export function morphIndex(preset: AppPreset, beat: number): number {
  return beat - preset.leftSteps.length;
}

/** Digi invoice layers cut so far. Empty during the rented walk. */
export function revealedLayers(preset: AppPreset, beat: number): LayerId[] {
  const at = morphIndex(preset, beat);
  if (at < 0) return [];
  const layers = preset.morphSteps.slice(0, at + 1).flatMap((step) => step.layers);
  return [...new Set(layers)];
}

/** Box ids whose labels have flipped to digithings by this beat. */
export function swappedBoxes(preset: AppPreset, beat: number): string[] {
  const at = morphIndex(preset, beat);
  if (at < 0) return [];
  return [...new Set(preset.morphSteps.slice(0, at + 1).flatMap((step) => step.boxes))];
}

export function emailSwapped(preset: AppPreset, beat: number): boolean {
  const at = morphIndex(preset, beat);
  if (at < 0) return false;
  return preset.morphSteps.slice(0, at + 1).some((step) => step.email);
}

/** Last beat whose top has crossed `line`. Earlier beats stay put until then. */
export function beatAtLine(tops: readonly number[], line: number): number {
  let index = 0;
  for (let i = 0; i < tops.length; i++) {
    if (tops[i] <= line) index = i;
  }
  return index;
}

/** Map an SVG bbox into the element's CSS box under `meet` letterboxing. */
export function meetBox(
  bb: { x: number; y: number; width: number; height: number },
  viewBox: { x: number; y: number; width: number; height: number },
  el: { width: number; height: number },
): { x: number; y: number; w: number; h: number } {
  if (viewBox.width <= 0 || viewBox.height <= 0 || el.width <= 0 || el.height <= 0) {
    return { x: 0, y: 0, w: 0, h: 0 };
  }
  const scale = Math.min(el.width / viewBox.width, el.height / viewBox.height);
  const offsetX = (el.width - viewBox.width * scale) / 2;
  const offsetY = (el.height - viewBox.height * scale) / 2;
  return {
    x: offsetX + (bb.x - viewBox.x) * scale,
    y: offsetY + (bb.y - viewBox.y) * scale,
    w: bb.width * scale,
    h: bb.height * scale,
  };
}
