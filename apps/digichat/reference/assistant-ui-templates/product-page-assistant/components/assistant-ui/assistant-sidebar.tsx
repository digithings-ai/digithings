import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import type { FC, ReactNode } from "react";

type AssistantSidebarProps = {
  children: ReactNode;
  assistant: ReactNode;
};

export const AssistantSidebar: FC<AssistantSidebarProps> = ({ children, assistant }) => {
  return (
    <ResizablePanelGroup orientation="horizontal">
      <ResizablePanel>{children}</ResizablePanel>
      <ResizableHandle />
      <ResizablePanel>{assistant}</ResizablePanel>
    </ResizablePanelGroup>
  );
};
