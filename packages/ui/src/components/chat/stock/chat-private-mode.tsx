"use client";

import {
  createContext,
  useContext,
  useEffect,
  useSyncExternalStore,
  type ReactNode,
} from "react";

/**
 * The one private-session flag every skin's export reads.
 *
 * Private mode keeps the typed text out of files: the stored messages still
 * hold it, and an export (its file name carries a slug of the question)
 * would hand it over. The host owns the session flag and passes it to
 * `ThreadSkinView`, which wraps every skin in `ChatPrivateModeProvider`.
 *
 * Two readers:
 * - React (`useChatPrivateMode`) for the menus, which render nothing.
 * - Plain code (`isChatPrivateMode`) for the export runners, which refuse.
 *   A mounted private scope counts until it unmounts or turns the mode off.
 */
let privateScopes = 0;
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

/** True while any mounted chat is in a private session. */
export function isChatPrivateMode(): boolean {
  return privateScopes > 0;
}

export function subscribeChatPrivateMode(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

const ChatPrivateModeContext = createContext(false);

export function ChatPrivateModeProvider({
  privateMode,
  children,
}: {
  privateMode?: boolean | undefined;
  children: ReactNode;
}) {
  const on = privateMode === true;
  useEffect(() => {
    if (!on) return;
    privateScopes += 1;
    emit();
    return () => {
      privateScopes -= 1;
      emit();
    };
  }, [on]);
  return <ChatPrivateModeContext.Provider value={on}>{children}</ChatPrivateModeContext.Provider>;
}

/** The private flag for this chat (its provider) or any mounted private chat. */
export function useChatPrivateMode(): boolean {
  const scoped = useContext(ChatPrivateModeContext);
  const anywhere = useSyncExternalStore(subscribeChatPrivateMode, isChatPrivateMode, () => false);
  return scoped || anywhere;
}
