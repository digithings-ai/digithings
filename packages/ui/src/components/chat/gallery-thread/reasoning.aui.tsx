"use client";

// Single source of truth lives in `../stock/reasoning.aui` (byte-identical
// fork removed, S24 review). This shim preserves the gallery-thread import
// path; import from either path — exports are identical.
export {
  Reasoning,
  ReasoningGroup,
  ReasoningRoot,
  ReasoningTrigger,
  ReasoningContent,
  ReasoningText,
  ReasoningFade,
  reasoningVariants,
} from "../stock/reasoning.aui";
export type { ReasoningRootProps } from "../stock/reasoning.aui";
