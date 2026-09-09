"use client";

import { SupportAssistantShell } from "@/components/support/support-assistant-shell";
import { useSupportConfig } from "@/lib/support/config-provider";
import { supportSettings } from "@/lib/support/settings";
import { createSupportToolkit } from "@/lib/support/toolkit";
import {
  AssistantRuntimeProvider,
  CompositeAttachmentAdapter,
  SimpleImageAttachmentAdapter,
  SimpleTextAttachmentAdapter,
  Suggestions,
  Tools,
  useAui,
  useAuiEvent,
  type Attachment,
  type AttachmentAdapter,
  type PendingAttachment,
} from "@assistant-ui/react";
import { AssistantChatTransport, useChatRuntime } from "@assistant-ui/react-ai-sdk";
import { lastAssistantMessageIsCompleteWithToolCalls } from "ai";
import { AlertCircleIcon } from "lucide-react";
import { useMemo, useState } from "react";

class SupportTextAttachmentAdapter extends SimpleTextAttachmentAdapter {
  accept = "text/plain,application/json,.txt,.log,.json";
}

class SizeLimitedAttachmentAdapter implements AttachmentAdapter {
  accept: string;

  constructor(
    private adapter: AttachmentAdapter,
    private maxSizeBytes: number,
  ) {
    this.accept = adapter.accept;
  }

  add(state: { file: File }) {
    if (state.file.size > this.maxSizeBytes) {
      throw new Error(
        `Attachments must be ${supportSettings.attachmentLimits.maxSizeMb} MB or smaller.`,
      );
    }
    return this.adapter.add(state);
  }

  send(attachment: PendingAttachment) {
    return this.adapter.send(attachment);
  }

  remove(attachment: Attachment) {
    return this.adapter.remove(attachment);
  }
}

export const Assistant = () => {
  const { assistant } = useSupportConfig();
  const searchParams =
    typeof window === "undefined" ? null : new URLSearchParams(window.location.search);
  const previewToken = searchParams?.get("p") ?? null;
  const previewSessionId = searchParams?.get("s") ?? null;
  const previewVersion = searchParams?.get("v") ?? null;
  const attachmentAdapter = useMemo(() => {
    const adapter = new CompositeAttachmentAdapter([
      new SimpleImageAttachmentAdapter(),
      new SupportTextAttachmentAdapter(),
    ]);
    return new SizeLimitedAttachmentAdapter(
      adapter,
      supportSettings.attachmentLimits.maxSizeMb * 1024 * 1024,
    );
  }, []);

  const runtime = useChatRuntime({
    sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithToolCalls,
    adapters: {
      attachments: attachmentAdapter,
    },
    transport: new AssistantChatTransport({
      api: "/api/chat",
      body: {
        previewToken,
        previewSessionId,
        previewVersion,
      },
    }),
  });

  const aui = useAui({
    tools: Tools({
      toolkit: createSupportToolkit(assistant, {
        previewToken,
        previewSessionId,
        previewVersion,
      }),
    }),
    suggestions: Suggestions([...assistant.suggestedPrompts]),
  });

  return (
    <AssistantRuntimeProvider aui={aui} runtime={runtime}>
      <AttachmentErrorNotice />
      <SupportAssistantShell />
    </AssistantRuntimeProvider>
  );
};

function AttachmentErrorNotice() {
  const [message, setMessage] = useState<string | null>(null);

  useAuiEvent("composer.attachmentAddError", ({ reason, message }) => {
    if (reason === "not-accepted") {
      setMessage("Use PNG, JPG, WebP, TXT, LOG, or JSON files up to 5 MB for this template.");
    } else {
      setMessage(message || "Attachment could not be added.");
    }
    window.setTimeout(() => setMessage(null), 4500);
  });

  if (!message) return null;

  return (
    <div className="fixed bottom-24 right-4 z-50 flex max-w-sm items-start gap-2 rounded-lg border border-red-200 bg-white p-3 text-sm text-red-800 shadow-lg">
      <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}
