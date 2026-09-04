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
export { GitHubGlyph, GoogleGlyph, LinkedInGlyph, XGlyph } from "./components/icons";
export {
  SocialRow,
  DIGITHINGS_SOCIALS,
  type SocialRowProps,
  type SocialProfile,
  type SocialNetwork,
} from "./components/SocialRow";
export {
  AuthCard,
  passwordStrength,
  type AuthCardLayout,
  type AuthCardMode,
  type AuthCardProps,
  type AuthOAuthProvider,
} from "./components/account/AuthCard";
export { ScrollyGraph, GraphSVG } from "./components/graph";
export {
  Nav,
  Footer,
  Colophon,
  ModuleCard,
  isNavGroup,
  type NavLink,
  type NavGroup,
  type NavItem,
} from "./components/chrome";
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
// promoted primitives (#1450)
export { WordReveal, type WordRevealProps } from "./components/typography/WordReveal";
export { Marquee, type MarqueeItem, type MarqueeProps } from "./components/marquee/Marquee";
export {
  TerminalManifest,
  type TerminalManifestRow,
  type TerminalManifestStatus,
  type TerminalManifestProps,
} from "./components/TerminalManifest";
export { DeckStack, DeckCard, type DeckStackProps, type DeckCardProps } from "./components/deck/DeckStack";
// chat family (#1418)
export { ChatTranscript, type ChatTranscriptProps } from "./components/chat/ChatTranscript";
export { ChatMessage, type ChatMessageProps, type ChatRole, type ChatTone } from "./components/chat/ChatMessage";
export { ChatStreamCursor, type ChatStreamCursorProps } from "./components/chat/ChatStreamCursor";
export { ChatMarkdown, type ChatMarkdownProps } from "./components/chat/ChatMarkdown";
export {
  ChatMarkdownSource,
  type ChatMarkdownSourceProps,
  type CodeBlockOverride,
} from "./components/chat/ChatMarkdownSource";
export { ChatMermaidBlock, type ChatMermaidBlockProps } from "./components/chat/ChatMermaidBlock";
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

// terminal loaders — the house type-out applied to waiting. Styles:
// @digithings/web/styles/terminal-loaders.css (needs chat-core.css first).
export { TerminalStepCaret, type TerminalStepCaretProps } from "./components/terminal/TerminalStepCaret";
export {
  ContainerBootLoader,
  CONTAINER_BOOT_STEPS,
  type ContainerBootLoaderProps,
} from "./components/terminal/ContainerBootLoader";
export {
  ChatResponseLoader,
  CHAT_RESPONSE_STEPS,
  CHAT_RESPONSE_HOLD_MS,
  type ChatResponseLoaderProps,
} from "./components/terminal/ChatResponseLoader";

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
  Dialog,
  DialogTrigger,
  DialogClose,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableRow,
  TableHead,
  TableCell,
  TableCaption,
  Breadcrumbs,
  Pagination,
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
  type DialogContentProps,
  type TableDensity,
  type Crumb,
  type PaginationProps,
  type TooltipContentProps,
} from "./components/controls";

// controls family — promoted controls patterns (#1548)
export {
  Skeleton,
  SkeletonGroup,
  type SkeletonProps,
  type SkeletonGroupProps,
  type SkeletonVariant,
} from "./components/controls/Skeleton";
export {
  EmptyState,
  type EmptyStateProps,
  type EmptyStateVariant,
  type EmptyStateDress,
} from "./components/controls/EmptyState";
export {
  SegmentedControl,
  Pager,
  PagerPage,
  IconButton,
  type SegmentedControlProps,
  type SegmentedOption,
  type PagerProps,
  type PagerPageProps,
  type IconButtonProps,
} from "./components/controls/NavButtons";
export {
  DatePager,
  formatDatePagerLabel,
  type DatePagerProps,
} from "./components/controls/DatePager";
export { TagsInput, TagChip, type TagsInputProps, type TagChipProps } from "./components/controls/TagsInput";
export { SearchBar, type SearchBarProps } from "./components/controls/SearchBar";
export { Field } from "./components/controls/Field";
export { Checkbox, RadioGroup, Radio, Switch } from "./components/controls/Selection";
export {
  Select,
  SelectTrigger,
  SelectValue,
  SelectPopup,
  SelectItem,
  SelectItemIndicator,
  SelectSeparator,
} from "./components/controls/Select";
export { Slider, sliderFill, type SliderProps } from "./components/controls/Slider";

// conviction family — dashboard F6 vocabulary, promoted verbatim
export { ConvictionMeter, SignedConvictionBadge } from "./components/conviction";

// contact family — Cloudflare-safe mailto link, promoted from the app forks
export { ContactMailto, buildMailtoHref } from "./components/contact";

// finance-charts family (#1450)
export {
  PriceChart,
  EquityCurve,
  DrawdownPlot,
  useFinanceChart,
  useFinanceChartPalette,
  getFinancePalette,
  readFinancePalette,
  financeChartOptions,
  tokenAlpha,
  toChartTime,
  useLightweightChart,
  chartChromeOptions,
  hostMonoFont,
  toLineData,
  timeToISO,
  useChartTip,
  ChartTipShell,
  PRICE_CHART_DEMO,
  EQUITY_CURVE_DEMO,
  DRAWDOWN_DEMO,
  type PriceChartProps,
  type EquityCurveProps,
  type DrawdownPlotProps,
  type FinanceChartPalette,
  type FinanceSeriesPoint,
  type OhlcPoint,
  type CrosshairLabelToken,
  type ChartChrome,
  type ChartTip,
  type UseLightweightChartConfig,
  type UseLightweightChartResult,
} from "./components/finance-charts";

// finance-composites family (#1450)
export {
  StockTicker,
  OrderBook,
  SortableTable,
  PerformanceDashboard,
  SyncedTearsheet,
  type TickerItem,
  type StockTickerProps,
  type OrderBookLevel,
  type OrderBookProps,
  type SortableColumn,
  type SortableTableProps,
  type DashboardHeadline,
  type DashboardRatio,
  type DashboardAllocation,
  type PerformanceDashboardProps,
  type TearsheetPoint,
  type SyncedTearsheetProps,
} from "./components/finance-composites";

// data-layout family (#1450)
export {
  Odometer,
  OdometerStrip,
  DotMatrixStat,
  BentoGrid,
  BentoCell,
  ProductFrame,
  FeatureCell,
  TestimonialWall,
  type OdometerStat,
  type DotMatrixStatProps,
  type BentoSpan,
  type ProductFrameProps,
  type FeatureCellProps,
  type TestimonialQuote,
  type TestimonialWallProps,
} from "./components/data-layout";

// effects-chrome family (#1450)
export {
  Pipeline,
  RotatingPrompts,
  StackingPanels,
  AnnouncementBar,
  TabStrip,
  tabBaseId,
  tabId,
  tabPanelId,
  ToastStack,
  type PipelineProps,
  type PipelineColumn,
  type PipelineNode,
  type PipelineStatus,
  type PipelineSummaryItem,
  type RotatingPromptsProps,
  type StackingPanelsProps,
  type StackingPanel,
  type AnnouncementBarProps,
  type TabStripProps,
  type TabItem,
  type ToastStackProps,
  type ToastItem,
  type ToastTone,
} from "./components/effects-chrome";

// finance-tearsheet family (#1463) — print-grade SVG tearsheet grammar
// (charts share one ViewWindow; the PDF pipeline re-renders them, so SVG is
// a hard constraint — see frontend/digiweb/CHARTS.md for the canvas split)
export {
  CandlestickChart,
  TimeSeries,
  MultiTimeSeries,
  RiskBandStrip,
  AllocationStepChart,
  SignedBars,
  ContributionReturnChart,
  TradeReturnChart,
  ReturnsMatrix,
  SegToggle,
  ChartLegend,
  ChartResetButton,
  KpiStrip,
  Kpi,
  TradeLogTable,
  DirectionPill,
  TearsheetCard,
  TearsheetCardKpis,
  TearsheetCardKpi,
  LiveBadge,
  LOOKBACK_OPTIONS,
  MIN_VIEW,
  clampView,
  viewWindowForPreset,
  viewWindowLastYear,
  matchLookbackPreset,
  viewsNear,
  PRINT_FULL_VIEW,
  runTearsheetPrint,
  isOpenTrade,
  fmtCompact,
  fmtPct,
  fmtMoney,
  fmtNum,
  toneClass,
  dailyReturnsFromEquity,
  annualizedVolPct,
  computeLivePerformanceKpis,
  computeLiveVsMarkPct,
  dayReturnAnchorNav,
  derivePriceAsOfDate,
  inceptionSignAgreesWithBase100,
  informationRatioFromDaily,
  olsBeta,
  overlappingDailyReturns,
  relativeMetricsFromReturnSeries,
  sinceInceptionPctFromNav,
  MIN_OVERLAP_DAYS,
  TEARSHEET_DEMO,
  RISK_BANDS,
  riskBandLabel,
  dcaRateCopy,
  type RiskBand,
  type CandlestickChartProps,
  type TimeSeriesProps,
  type MultiTimeSeriesProps,
  type OverlaySeries,
  type RiskBandStripProps,
  type AllocationStepChartProps,
  type AllocationFillMarker,
  type OverlayTone,
  type ChartLegendKind,
  type SignedBarsProps,
  type ContributionReturnChartProps,
  type ContributionReturnPoint,
  type TradeReturnChartProps,
  type ReturnsPeriod,
  type MatrixMetric,
  type ChartScale,
  type ChartTone,
  type ViewWindow,
  type LookbackPreset,
  type KpiStripProps,
  type KpiProps,
  type TradeLogTableProps,
  type TradeLogColumn,
  type TradeLogRow,
  type TearsheetCardProps,
  type LiveBadgeProps,
  type TearsheetSeriesPoint,
  type TearsheetOhlcBar,
  type TearsheetTrade,
  type TradeReturnBar,
  type LiveKpiPosition,
  type LiveKpiNavPoint,
  type LiveKpiBenchmarkPoint,
  type LivePerformanceKpis,
  type LivePerformanceKpisInput,
} from "./components/finance-tearsheet";

// repo-activity family (#3445) — snapshot-first GitHub velocity, compact + detailed
export {
  RepoActivity,
  fetchRepoActivityLive,
  cloneParts,
  grouped,
  isoDay,
  DEFAULT_LIVE_TIMEOUT_MS,
  REPO_ACTIVITY_DEMO,
  REPO_ACTIVITY_DEMO_CLONE,
  REPO_ACTIVITY_DEMO_CONTRIBUTING,
  REPO_ACTIVITY_DEMO_URL,
  type RepoActivityProps,
  type RepoActivityLiveConfig,
  type RepoActivitySnapshot,
  type RepoFeature,
  type RepoIssueItem,
  type RepoModuleActivity,
  type RepoPullItem,
  type RepoRelease,
  type FetchRepoActivityLiveOptions,
} from "./components/repo-activity";

export { modules, edges, moduleById, type ModuleNode, type StackItem, type Tier } from "./data/modules";
export { subsystems, subsystemById, type Subsystem } from "./data/subsystems";

// chrome (command palette) + symbols (brand marks) promotions (#1548)
export {
  CommandPalette,
  type CommandPaletteProps,
  type CommandPaletteGroup,
  type CommandPaletteItem,
} from "./components/command-palette";
export {
  DigiquantMark,
  Wordmark,
  type DigiquantMarkProps,
  type WordmarkProps,
} from "./components/symbols/marks";
// Terminal identity — the `digi` + block-cursor lockup and the hairline display
// cut. Supersedes `Wordmark` for new work; `Wordmark`/`Colophon` stay for the
// surfaces already using them.
export {
  TerminalMark,
  TerminalWordmark,
  HairlineWordmark,
  TERMINAL_CURSOR,
  type TerminalMarkProps,
  type TerminalWordmarkProps,
  type HairlineWordmarkProps,
} from "./components/symbols/terminal-marks";
export {
  AnimatedLockup,
  MODULE_SUFFIXES,
  type AnimatedLockupProps,
} from "./components/symbols/terminal-lockup";
