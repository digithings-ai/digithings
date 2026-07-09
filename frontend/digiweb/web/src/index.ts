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
export { GitHubGlyph } from "./components/icons";
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

// controls layer (#1419)
export { Button, type ButtonProps, type ButtonDress, type ButtonReferenceVariant, type ButtonChatVariant, type ButtonChatSize } from "./components/controls/Button";
export { Badge, type BadgeProps, type BadgeDress, type BadgeReferenceVariant, type BadgeChatVariant } from "./components/controls/Badge";
export { Card, CardHeader, CardTitle, CardDescription, CardAction, CardContent, CardFooter, type CardProps, type CardDress, type CardSize } from "./components/controls/Card";
export { Input, type InputProps, type InputDress } from "./components/controls/Input";
export { Label, type LabelProps, type LabelDress } from "./components/controls/Label";
export { Avatar, AvatarImage, AvatarFallback, AvatarBadge, AvatarGroup, AvatarGroupCount, type AvatarProps, type AvatarImageProps, type AvatarFallbackProps, type AvatarSize } from "./components/controls/Avatar";
export {
  DropdownMenu,
  DropdownMenuPortal,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuItem,
  DropdownMenuCheckboxItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
  Sheet,
  SheetTrigger,
  SheetClose,
  SheetPortal,
  SheetOverlay,
  SheetContent,
  SheetHeader,
  SheetFooter,
  SheetTitle,
  SheetDescription,
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
  type ControlSkin,
  type DropdownMenuContentProps,
  type DropdownMenuItemProps,
  type SheetContentProps,
  type TooltipContentProps,
} from "./components/controls";

export { modules, edges, moduleById, type ModuleNode, type StackItem, type Tier } from "./data/modules";
export { subsystems, subsystemById, type Subsystem } from "./data/subsystems";
