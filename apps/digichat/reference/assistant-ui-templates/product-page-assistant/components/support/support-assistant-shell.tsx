"use client";

import { AssistantModal } from "@/components/assistant-ui/assistant-modal";
import { Thread, type ThreadLabels } from "@/components/assistant-ui/thread";
import { useSupportConfig } from "@/lib/support/config-provider";

export function SupportAssistantShell() {
  const { assistant } = useSupportConfig();
  const threadLabels: ThreadLabels = {
    composerPlaceholder: assistant.labels.composerPlaceholder,
    composerInput: assistant.labels.composerInput,
    uploadButton: assistant.labels.uploadButton,
    send: assistant.labels.send,
    cancel: assistant.labels.cancel,
    copy: assistant.labels.copy,
    refresh: assistant.labels.refresh,
    more: assistant.labels.more,
    edit: assistant.labels.edit,
    previous: assistant.labels.previous,
    next: assistant.labels.next,
    scrollToBottom: assistant.labels.scrollToBottom,
    export: assistant.labels.export,
  };

  return (
    <AssistantModal
      triggerLabel={assistant.labels.modalTrigger}
      closeLabel={assistant.labels.modalClose}
      defaultOpen
    >
      <Thread labels={threadLabels} welcome={assistant.welcome} />
    </AssistantModal>
  );
}
