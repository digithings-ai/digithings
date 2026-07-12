import type { ReactNode } from "react";

export type VaultHitSummary = { title: string; path: string };

export type DigiChatActivity =
  | { kind: "status"; message: string }
  | { kind: "tool_call"; name: string; query: string }
  | {
      kind: "tool_result";
      name: string;
      query: string;
      hits: VaultHitSummary[];
      count: number;
    }
  | { kind: "reasoning"; text: string }
  | { kind: "trace"; label: string; done: boolean };

export type DigiChatMessage = {
  role: "user" | "assistant";
  content: string;
  activities?: DigiChatActivity[];
};

export type DigiChatBranding = {
  title?: string;
  /** e.g. "by digichat" link target */
  attributionUrl?: string;
  attributionLabel?: string;
};

export type DigiChatSessionConfig = {
  welcomeIntro: string;
  suggestions?: string[];
  placeholder: string;
  showByok: boolean;
  /** Collapsible status bar with wordmark + model (digithings-web /chat). */
  showStatusBar?: boolean;
  branding?: DigiChatBranding;
  ariaLabel?: string;
  className?: string;
  /** page = full viewport under nav; embed = flex child inside iframe shell */
  layout?: "page" | "embed";
};

export type DigiChatController = {
  messages: DigiChatMessage[];
  busy: boolean;
  error: string | null;
  quotaPrompt?: boolean;
  send: (question: string) => void | Promise<void>;
  stop?: () => void;
  onRetry?: () => void;
  modelLabel?: string;
  providerIsSet?: boolean;
  openSettings?: () => void;
};

export type DigiChatSessionProps = DigiChatSessionConfig & {
  chat: DigiChatController;
  headerSlot?: ReactNode;
  footerSlot?: ReactNode;
  /** Replaces the input form (e.g. embed paywall). */
  formReplacement?: ReactNode;
  settingsPanel?: ReactNode;
  /** Override assistant markdown rendering (e.g. mermaid in digithings-web). */
  renderAssistantContent?: (content: string, streaming: boolean) => ReactNode;
  /** When false, skip streaming intro (e.g. resumed handoff with messages). */
  showIntro?: boolean;
};
