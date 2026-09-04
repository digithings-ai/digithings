export { DigiChatSession } from "./DigiChatSession";
export { useStreamingIntro } from "./useStreamingIntro";
export { CopyButton } from "./components/CopyButton";
export { DigiChatMark, DigiChatWordmark } from "./components/DigiChatMark";
export { ChatActivities } from "./components/ChatActivities";
export { MiniMarkdown } from "./components/MiniMarkdown";
export { DocumentPane } from "./components/DocumentPane";
export {
  toCanonRows,
  outcomeMeta,
  citationHits,
  readableSnippet,
  toolDisplayName,
  stripFoundryCitationMarkers,
  type CanonActivityRow,
} from "./activity-view";
export {
  serializeAssistantMarkdown,
  serializeThreadMarkdown,
  copyMarkdownWithFallback,
  downloadMarkdown,
  type TranscriptTurn,
  type TranscriptSource,
  type CopyMarkdownResult,
} from "./transcript-markdown";
export {
  parseSlashInput,
  matchingSlashCommands,
  SLASH_COMMANDS,
  LANG_LABELS,
  type SlashDef,
} from "./slash-commands";
export type {
  DigiChatActivity,
  DigiChatBranding,
  DigiChatController,
  DigiChatMessage,
  DigiChatSessionConfig,
  DigiChatSessionProps,
  VaultHitSummary,
} from "./types";
