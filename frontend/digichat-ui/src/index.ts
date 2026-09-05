export { CopyButton } from "./components/CopyButton";
export { DigiChatMark, DigiChatWordmark } from "./components/DigiChatMark";
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
  downloadTextFile,
  downloadPlainText,
  downloadHtml,
  markdownToPlainText,
  markdownToHtmlDocument,
  truncateForMailto,
  buildMailtoUrl,
  buildAnswerMailto,
  buildThreadMailto,
  openMailtoWithFallback,
  printTranscriptWithFallback,
  MAILTO_MAX_ENCODED_LEN,
  MAILTO_TRUNCATION_NOTE,
  type TranscriptTurn,
  type TranscriptSource,
  type CopyMarkdownResult,
  type TruncateForMailtoResult,
  type MailtoOpenResult,
  type PrintTranscriptResult,
} from "./transcript-markdown";
export {
  parseSlashInput,
  matchingSlashCommands,
  slashHelpText,
  nextPaletteIndex,
  formatCliSettingLine,
  isLangCode,
  SLASH_COMMANDS,
  LANG_CODES,
  LANG_LABELS,
  LANG_CHOICES,
  type SlashDef,
  type SlashId,
  type SlashVisibility,
  type CliSettingRow,
  type LangCode,
} from "./slash-commands";
export type {
  DigiChatActivity,
  DigiChatController,
  DigiChatMessage,
  VaultHitSummary,
} from "./types";
