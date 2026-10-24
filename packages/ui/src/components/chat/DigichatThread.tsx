"use client";

/**
 * First-party digichat Thread — the gallery `/chatbot` Thread module
 * (`gallery-thread/thread.aui.tsx` + slots + chatbot.css), not a parallel
 * ChatMarkdown / ChatThinking / ChatToolCall tree.
 */
import type { FormEvent, ReactNode } from "react";

import {
  Thread,
  type ComposerLayout,
  type GroupDisclosureMode,
  type ThreadComponents,
  type ThreadGroupPart,
  type ThreadProps,
  type ThreadSlashTrigger,
  type ThreadMentionTrigger,
} from "./gallery-thread/thread.aui";
import type { WorkVisibility } from "./stock/skin-types";
import type { ScrollMode } from "./gallery-thread/scroll-mode";

export type DigichatThreadProps = {
  welcome?: string;
  /** Subparagraphs under the headline. Deploy `chrome.welcome.body`. */
  welcomeBody?: readonly string[];
  /** Welcome-state example prompts. Deploy `chrome.suggestions`. */
  suggestions?: readonly string[];
  placeholder?: string;
  className?: string;
  /** Embed send-gate / system page-context attach. Form onSubmit. */
  onComposerSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  composerLayout?: ComposerLayout;
  components?: ThreadComponents;
  /** Native `/` trigger popover (`unstable_useSlashCommandAdapter`). */
  slash?: ThreadSlashTrigger;
  /** Native `@` mention popover for catalog tools. */
  mention?: ThreadMentionTrigger;
  /** Attachment names whose chips render nowhere (file part still reaches the model). */
  hiddenAttachmentNames?: readonly string[];
  /** Deploy `reasoning` disclosure mode. Defaults to `collapsed`. */
  reasoningMode?: GroupDisclosureMode;
  /** Deploy `toolCalls` disclosure mode. Defaults to `collapsed`. */
  toolCallsMode?: GroupDisclosureMode;
  /** How much of the agent's work the user sees: quiet | balanced | verbose. */
  workVisibility?: WorkVisibility;
  /** Row rendered inside the composer border, under the input. */
  composerToolbar?: ReactNode;
  /** `always` reserves a scrollbar gutter; `auto` shows bars only on scroll. */
  scrollbars?: "always" | "auto";
  /** Worked-chain rhythm. `default` is the fixed spacing. */
  density?: "compact" | "default" | "airy";
  /** `follow` chases the stream; `free` never moves the viewport. */
  scrollMode?: ScrollMode;
};

export function DigichatThread({
  welcome = "What should we inspect?",
  welcomeBody = [],
  suggestions,
  placeholder = "Ask digichat…",
  className,
  onComposerSubmit,
  composerLayout,
  components,
  slash,
  mention,
  hiddenAttachmentNames,
  reasoningMode,
  toolCallsMode,
  workVisibility,
  composerToolbar,
  scrollbars,
  density = "default",
  scrollMode,
}: DigichatThreadProps) {
  return (
    <Thread
      welcome={welcome}
      welcomeBody={welcomeBody}
      suggestions={suggestions}
      placeholder={placeholder}
      className={className}
      onComposerSubmit={onComposerSubmit}
      composerLayout={composerLayout}
      components={components}
      slash={slash}
      mention={mention}
      hiddenAttachmentNames={hiddenAttachmentNames}
      reasoningMode={reasoningMode}
      toolCallsMode={toolCallsMode}
      workVisibility={workVisibility}
      composerToolbar={composerToolbar}
      scrollbars={scrollbars}
      density={density}
      scrollMode={scrollMode}
    />
  );
}

export {
  Thread,
  type ComposerLayout,
  type GroupDisclosureMode,
  type ThreadComponents,
  type ThreadGroupPart,
  type ThreadProps,
  type ThreadSlashTrigger,
  type ThreadMentionTrigger,
};
