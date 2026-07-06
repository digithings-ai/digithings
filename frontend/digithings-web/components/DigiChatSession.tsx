"use client";

import { useEffect, useState } from "react";
import {
  DigiChatSession as SharedDigiChatSession,
  type DigiChatController,
} from "@digithings/digichat-ui";
import { useStackChat } from "@/lib/useStackChat";
import { readAndClearHandoff } from "@/lib/chatHandoff";
import { MiniMarkdown } from "@/lib/miniMarkdown";
import { ProviderSettings } from "@/components/ProviderSettings";
import { providerSummary, useProviderSettings } from "@/lib/providerSettings";

const INTRO = `digichat — the assistant for the digithings stack.

Ask about the architecture: how the modules fit together, how it's built, how it runs. I search digivault (the docs) before answering, so I cite real docs rather than guess.

Free tier uses OpenRouter's model pool — no key needed. Or bring your own key (OpenRouter, OpenAI, Anthropic, Gemini) for any model.

Try asking for a diagram of a pipeline.`;

const SUGGESTIONS = [
  "What does digigraph orchestrate?",
  "Diagram the digiquant backtest pipeline",
  "How does auth work in digikey?",
  "How is the stack built?",
];

export function DigiChatSession() {
  const provider = useProviderSettings();
  const { messages, busy, error, quotaPrompt, send, stop, seed, clearQuotaPrompt } =
    useStackChat([], provider);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [showIntro, setShowIntro] = useState(true);

  const openSettings = () => {
    clearQuotaPrompt();
    setSettingsOpen(true);
  };

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    const h = readAndClearHandoff();
    if (h && (h.messages.length || h.pending)) {
      if (h.messages.length) {
        seed(h.messages);
        setShowIntro(false);
      }
      if (h.pending) void send(h.pending);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  const chat: DigiChatController = {
    messages,
    busy,
    error,
    quotaPrompt,
    send,
    stop,
    modelLabel: providerSummary(provider),
    providerIsSet: provider.isSet,
    openSettings,
  };

  return (
    <SharedDigiChatSession
      welcomeIntro={INTRO}
      suggestions={SUGGESTIONS}
      placeholder="ask digichat"
      showByok
      showStatusBar
      layout="page"
      chat={chat}
      showIntro={showIntro}
      renderAssistantContent={(content) => (content ? <MiniMarkdown text={content} /> : null)}
      settingsPanel={
        <ProviderSettings
          open={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          apiKey={provider.apiKey}
          provider={provider.provider}
          model={provider.model}
          isSet={provider.isSet}
          onSave={provider.save}
          onClear={provider.clear}
        />
      }
    />
  );
}
