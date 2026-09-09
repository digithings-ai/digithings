"use client";

/**
 * First-party digichat Thread — the gallery `/chatbot` Thread module
 * (`gallery-thread/thread.aui.tsx` + slots + chatbot.css), not a parallel
 * ChatMarkdown / ChatThinking / ChatToolCall tree.
 */
import type { FormEvent } from "react";

import {
  Thread,
  type ComposerLayout,
  type ThreadComponents,
  type ThreadGroupPart,
  type ThreadProps,
} from "./gallery-thread/thread.aui";

export type DigichatThreadProps = {
  welcome?: string;
  /** Subparagraphs under the headline. Deploy `chrome.welcome.body`. */
  welcomeBody?: readonly string[];
  placeholder?: string;
  className?: string;
  /** Embed send-gate / system page-context attach. Form onSubmit. */
  onComposerSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  composerLayout?: ComposerLayout;
  components?: ThreadComponents;
};

export function DigichatThread({
  welcome = "What should we inspect?",
  welcomeBody = [],
  placeholder = "Ask digichat…",
  className,
  onComposerSubmit,
  composerLayout,
  components,
}: DigichatThreadProps) {
  return (
    <Thread
      welcome={welcome}
      welcomeBody={welcomeBody}
      placeholder={placeholder}
      className={className}
      onComposerSubmit={onComposerSubmit}
      composerLayout={composerLayout}
      components={components}
    />
  );
}

export {
  Thread,
  type ComposerLayout,
  type ThreadComponents,
  type ThreadGroupPart,
  type ThreadProps,
};
