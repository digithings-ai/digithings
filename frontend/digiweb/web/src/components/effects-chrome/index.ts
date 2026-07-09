/**
 * effects-chrome family barrel — scroll set pieces + site-chrome primitives
 * promoted from the design reference (#1450): Pipeline, RotatingPrompts,
 * StackingPanels, AnnouncementBar, TabStrip, ToastStack.
 *
 * Structural CSS for the whole family ships in styles/effects-chrome.css
 * (one sheet, imported plainly — it manages its own layering).
 */
export {
  Pipeline,
  type PipelineProps,
  type PipelineColumn,
  type PipelineNode,
  type PipelineStatus,
  type PipelineSummaryItem,
} from "./Pipeline";
export { RotatingPrompts, type RotatingPromptsProps } from "./RotatingPrompts";
export { StackingPanels, type StackingPanelsProps, type StackingPanel } from "./StackingPanels";
export { AnnouncementBar, type AnnouncementBarProps } from "./AnnouncementBar";
