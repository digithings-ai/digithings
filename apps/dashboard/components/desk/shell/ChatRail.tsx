'use client';

import DigichatPopup from '@/components/digichat-popup';

/** Right column. The existing digichat launcher docks here instead of floating. */
export function ChatRail({ onOpenChange }: { onOpenChange: (open: boolean) => void }) {
  return (
    <aside
      data-chat-rail=""
      aria-label="digichat"
      className="relative min-h-0 min-w-0 border-l border-hair bg-surface"
    >
      <DigichatPopup placement="rail" onRailOpenChange={onOpenChange} />
    </aside>
  );
}
