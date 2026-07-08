export { ThemeProvider, ThemeToggle, useTheme, themeInitScript } from "./components/ThemeProvider";
export { MotionProvider, Reveal, Stagger, HeroEntrance, useMotionSafe, m, EASE } from "./motion/primitives";
export {
  useScrollyFeatures,
  ScrollyRail,
  progressToIndex,
  scrollyTrackHeightVh,
  STEPPER_MEDIA_QUERY,
  type ScrollyFeatures,
  type UseScrollyFeaturesOptions,
} from "./motion/scrolly";
export { Emblem, emblems } from "./components/emblems";
export { StackLogo, StackRow } from "./components/StackLogo";
export { ScrollyGraph, GraphSVG } from "./components/graph";
export { Nav, Footer, Colophon, ModuleCard, type NavLink } from "./components/chrome";
export { NavShell, type NavShellProps } from "./components/NavShell";
export { DocsLayout, type DocsNavGroup, type DocsNavItem, type DocsHero } from "./components/docs/DocsLayout";
export { CodeTabs, DocsCodeBlock, type CodeSample } from "./components/docs/CodeTabs";
export { EndpointDoc, MethodBadge, type DocsEndpoint, type DocsField, type DocsMethod } from "./components/docs/Endpoint";
export { HashScrollManager } from "./navigation/HashScrollManager";
export {
  hashIdFromHref,
  instantScrollToHash,
  instantScrollToId,
  isSamePageHashHref,
} from "./navigation/hashScroll";
export { Terminal, type TermLine } from "./components/Terminal";

// promoted primitives (#1415)
export { Pricing, PricingTierCard, PrecisionTable, type PricingProps, type PricingTierCardProps, type PrecisionTableProps } from "./components/pricing/Pricing";
export { PricingMatrix, type PricingMatrixProps, type PricingMatrixTier, type PricingMatrixGroup, type PricingMatrixRow } from "./components/pricing/PricingMatrix";
export { NumberedStages, type NumberedStage } from "./components/stages/NumberedStages";
export { PerfMetrics, type PerfMetric } from "./components/metrics/PerfMetrics";
export { StatCounter, type CounterStat } from "./components/metrics/StatCounter";
export {
  TerminalManifest,
  type TerminalManifestRow,
  type TerminalManifestStatus,
  type TerminalManifestProps,
} from "./components/TerminalManifest";
// chat family (#1418)
export { ChatTranscript, type ChatTranscriptProps } from "./components/chat/ChatTranscript";
export { ChatMessage, type ChatMessageProps, type ChatRole, type ChatTone } from "./components/chat/ChatMessage";
export { ChatStreamCursor, type ChatStreamCursorProps } from "./components/chat/ChatStreamCursor";
export { ChatMarkdown, type ChatMarkdownProps } from "./components/chat/ChatMarkdown";
export { ChatCodeBlock, ChatCopyButton, type ChatCodeBlockProps, type ChatCopyButtonProps } from "./components/chat/ChatCodeBlock";
export { ChatToolCall, type ChatToolCallProps, type ChatToolCallStatus, type ChatToolCallLine } from "./components/chat/ChatToolCall";
export { ChatThinking, type ChatThinkingProps } from "./components/chat/ChatThinking";
export {
  ChatWidgetFrame,
  ChatWidgetButton,
  type ChatWidgetFrameProps,
  type ChatWidgetFrameVariant,
  type ChatWidgetButtonProps,
  type ChatWidgetButtonTone,
} from "./components/chat/ChatWidgetFrame";

export { modules, edges, moduleById, type ModuleNode, type StackItem, type Tier } from "./data/modules";
export { subsystems, subsystemById, type Subsystem } from "./data/subsystems";
