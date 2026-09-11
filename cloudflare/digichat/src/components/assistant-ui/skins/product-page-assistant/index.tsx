"use client";

import { Thread } from "@/app/(baseline)/stock/thread.aui";
import { AssistantModal } from "./assistant-modal";
import { ProductDashboard } from "./product-dashboard";
import { useComposerCopy } from "@/components/stock/skin-chrome";

export function ProductPageAssistant() {
  const { title } = useComposerCopy("How can I help?", "Describe the issue");
  const trigger = title ? `Open ${title}` : "Open support";
  return (
    <div className="relative h-full">
      <ProductDashboard />
      <AssistantModal triggerLabel={trigger} closeLabel="Close support" defaultOpen>
        <Thread />
      </AssistantModal>
    </div>
  );
}
