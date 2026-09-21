export {
  ThemeProvider,
  ThemeToggle,
  useTheme,
  themeInitScript,
  DirectionProvider,
  useDirection,
  type Direction,
} from "./components/ThemeProvider";
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
  Footer,
  Colophon,
  ModuleCard,
  SkipLink,
  CtaLink,
  IconLink,
  hrefIsCurrent,
  isNavGroup,
  type NavLink,
  type NavGroup,
  type NavItem,
  type CtaLinkProps,
  type IconLinkProps,
} from "./components/chrome";
export { NavShell, type NavShellProps } from "./components/NavShell";
export { DocsLayout, type DocsNavGroup, type DocsNavItem, type DocsHero } from "./components/docs/DocsLayout";
export { CodeTabs, DocsCodeBlock, type CodeSample } from "./components/docs/CodeTabs";
export { CopyCommand, type CopyCommandProps, type CopyCommandSample } from "./components/docs/CopyCommand";
export { EndpointDoc, MethodBadge, type DocsEndpoint, type DocsField, type DocsMethod } from "./components/docs/Endpoint";
export { HashScrollManager } from "./navigation/HashScrollManager";
export {
  hashIdFromHref,
  instantScrollToHash,
  instantScrollToId,
  isSamePageHashHref,
} from "./navigation/hashScroll";
export { Terminal, type TermLine } from "./components/Terminal";
// Spinner — the canonical inline loading glyph (replaces the hand-rolled
// `size-[11px] … border-current/30` span copied across reference specimens).
export { Spinner, type SpinnerProps } from "./components/Spinner";

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
export {
  DigichatLauncher,
  type DigichatLauncherProps,
} from "./components/chat/DigichatLauncher";
export { ChatMarkdown, type ChatMarkdownProps } from "./components/chat/ChatMarkdown";
// ChatMarkdownSource is internal to ChatMarkdown — not part of the public
// barrel (#3819). The legacy family stays exported for its remaining
// consumers: ChatMarkdown (dashboard SafeMarkdown styling shell, digichat-ui
// MiniMarkdown) and the ChatToolCallStatus type (digichat-ui activity view).
// No new adoption; ChatThinking/ChatToolCall components have no importers.
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
// @digithings/ui/styles/terminal-loaders.css (needs chat-core.css first).
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

// digichat boot loader — the default embed warm-up animation (composer-outline
// cube field). Styles: @digithings/ui/styles/digichat-boot-loader.css.
export {
  DigichatBootLoader,
  type DigichatBootLoaderProps,
} from "./components/chat/DigichatBootLoader";

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
// a hard constraint — see packages/ui/CHARTS.md for the canvas split)
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
  navHistoryForLiveOverlap,
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
  type ReferenceTone,
  type ReferenceLineSpec,
  type ReferenceBandSpec,
  type ReferenceMarkerSpec,
  type ChartReferences,
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
  RepoHeatmap,
  bucketDaily,
  levelFor,
  fetchRepoActivityLive,
  cloneParts,
  grouped,
  isoDay,
  DEFAULT_LIVE_TIMEOUT_MS,
  REPO_ACTIVITY_DEMO,
  REPO_ACTIVITY_DEMO_CLONE,
  REPO_ACTIVITY_DEMO_CONTRIBUTING,
  REPO_ACTIVITY_DEMO_URL,
  type HeatDay,
  type RepoActivityProps,
  type RepoHeatmapProps,
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
export {
  GLOOMBERB_ATTRIBUTION,
  GLOOMBERB_DELAY_NOTICE,
  GLOOMBERB_TERMINAL_URL,
  gloomberbTickerUrl,
  readGloomberbAttribution,
  type GloomberbAttribution,
} from "./lib/gloomberb";

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

// prose family (D1, #4429) — the shared long-form company/legal grammar
// (PageHead / RuledList / RuledRow / Mono), promoted from digithings-web's
// app-local `_company/prose.tsx`. Utilities only; no site/app CSS class.
export {
  Mono,
  PageHead,
  RuledList,
  RuledRow,
  type MonoProps,
  type PageHeadProps,
  type RuledListProps,
  type RuledRowProps,
} from "./components/prose";
// figure family (D1, #4429) — the numbered `Fig N` figure caption.
export { Figure, type FigureProps } from "./components/figure";
// document family (D1, #4429) — the framed-column marketing grammar
// (DocumentFrame / Section / PageTitle / Prose / GlyphList / GlyphRow): one
// bordered column, hairline section separators, a small document-scale type
// ladder, and the `[*]` + `<strong>Label</strong>` row. Utilities only; no
// site/app CSS class, so no census entry and nothing to add to styles/.
export {
  DocumentFrame,
  Section,
  PageTitle,
  Prose,
  GlyphList,
  GlyphRow,
  type DocumentFrameProps,
  type SectionProps,
  type PageTitleProps,
  type ProseProps,
  type GlyphListProps,
  type GlyphRowProps,
} from "./components/document";
