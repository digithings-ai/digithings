'use client';

import Link from 'next/link';
import { useAccess } from './Access';
import { ChatSessionsBlock } from './blocks-desk';
import { StateBlock } from './ui';

/**
 * Docked digichat rail. Sessions come from GET /chat/sessions.
 * A locked or missing chat page does not fetch. The thread stays on /tools/chat.
 */
export function ChatRail({ open }: { open: boolean }) {
  const { manifest } = useAccess();
  if (!open) return null;
  const page = manifest?.desks.flatMap((d) => d.pages).find((p) => p.path === '/tools/chat') ?? null;
  return (
    <aside id="chat-rail" className="chat-rail" aria-label="digichat">
      <div className="rail-head">
        <span>digichat</span>
        <Link href="/tools/chat">thread</Link>
      </div>
      {!manifest ? <p className="note mute">loading…</p>
        : !page || page.access !== 'granted'
          ? <StateBlock kind="empty" title="Locked." why={page?.reason ?? 'digichat is not on this caller.'} />
          : <ChatSessionsBlock />}
    </aside>
  );
}
