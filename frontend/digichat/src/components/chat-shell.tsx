"use client";

/**
 * ChatShell — authenticated chat chrome for digichat.
 *
 * #273: Rewritten to consume @digithings/design/app-shell-terminal
 * classes natively in React (CSS classes are the primitive's contract; the
 * primitive's vanilla-JS `initAppShell` would clobber React state by
 * imperatively rewriting the host's innerHTML, so we render the same DOM
 * shape in JSX and keep React authoritative over SSR, streaming, Auth.js,
 * and BYOK wiring).
 *
 * All existing plumbing preserved:
 *   - Local + remote thread state + debounced server save
 *   - Conversation hydration on demand
 *   - Auth.js session via props
 *   - BYOK / streaming / trace rendering all live in ChatPanel
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { UIMessage } from "ai";
import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { signOut } from "next-auth/react";
import Link from "next/link";
import { ChatPanel } from "@/components/chat-panel";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  filterThreadsByQuery,
  groupThreadsByDate,
} from "@/lib/conversation-sidebar";
import {
  canFlushServerMessages,
  loadLocalThreads,
  mergeRemoteAndLocal,
  saveLocalThreads,
  withHydratedConversation,
  type ChatThreadState,
} from "@/lib/thread-local";
import { cn } from "@/lib/utils";
import { p } from "@/lib/base-path";

type RemoteSummary = { id: string; title: string; updatedAt: string };

async function fetchConversationBody(
  id: string,
): Promise<{ title: string; messages: UIMessage[] } | null> {
  try {
    const r = await fetch(p(`/api/conversations/${id}`), { credentials: "include" });
    if (!r.ok) return null;
    return (await r.json()) as { title: string; messages: UIMessage[] };
  } catch {
    return null;
  }
}

const SLASH_REFERENCE: Array<{ cmd: string; hint: string }> = [
  { cmd: "/help", hint: "list commands" },
  { cmd: "/byok", hint: "BYOK (CLI)" },
  { cmd: "/websearch", hint: "toggle web search" },
  { cmd: "/settings", hint: "CLI settings panel" },
  { cmd: "/model", hint: "<id>" },
  { cmd: "/clear", hint: "clear thread" },
  { cmd: "/scope", hint: "show JWT scopes" },
  { cmd: "/history", hint: "focus sidebar" },
  { cmd: "/key", hint: "alias for /byok" },
];

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function ChatShell({
  userId,
  userEmail,
  displayName,
}: {
  userId: string;
  userEmail?: string | null;
  displayName?: string | null;
}) {
  const [threads, setThreads] = useState<ChatThreadState[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [serverPersistence, setServerPersistence] = useState(false);
  const [ready, setReady] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [byokMode, setByokMode] = useState(false);
  const [threadQuery, setThreadQuery] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  // Tracks whether the active rename gesture already resolved (Enter/Escape)
  // so the input's onBlur — which also fires on unmount — doesn't commit
  // after a cancel or double-commit after Enter.
  const renameHandledRef = useRef(false);

  const threadsRef = useRef(threads);
  useEffect(() => {
    threadsRef.current = threads;
  }, [threads]);

  const debouncedSaveRef = useRef<Record<string, ReturnType<typeof setTimeout> | undefined>>({});
  /** One-shot: next flush for this thread may intentionally clear server messages. */
  const allowTruncateRef = useRef<Record<string, boolean>>({});

  const flushServerSave = useCallback(
    async (threadId: string) => {
      if (!serverPersistence) return;
      let t = threadsRef.current.find((x) => x.id === threadId);
      if (!t) return;
      // PUT is a full replace. An unhydrated remote thread still has messages: []
      // from the list endpoint — flushing it would delete the real history.
      if (!canFlushServerMessages(t)) return;

      if (!t.remote) {
        const cr = await fetch(p("/api/conversations"), {
          method: "POST",
          credentials: "include",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ id: t.id, title: t.title }),
        });
        if (!cr.ok) return;
        setThreads((prev) => prev.map((x) => (x.id === threadId ? { ...x, remote: true } : x)));
        t = { ...t, remote: true };
      }

      const snap = threadsRef.current.find((x) => x.id === threadId) ?? t;
      if (!canFlushServerMessages(snap)) return;
      const allowTruncate = !!allowTruncateRef.current[threadId];
      delete allowTruncateRef.current[threadId];
      await fetch(p(`/api/conversations/${threadId}`), {
        method: "PUT",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          title: snap.title,
          messages: snap.messages,
          ...(allowTruncate ? { allowTruncate: true } : {}),
        }),
      });
    },
    [serverPersistence],
  );

  const scheduleServerSave = useCallback(
    (threadId: string) => {
      if (!serverPersistence) return;
      const prevTimer = debouncedSaveRef.current[threadId];
      if (prevTimer) clearTimeout(prevTimer);
      debouncedSaveRef.current[threadId] = setTimeout(() => {
        delete debouncedSaveRef.current[threadId];
        void flushServerSave(threadId);
      }, 650);
    },
    [flushServerSave, serverPersistence],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const local = loadLocalThreads(userId);
      let remote: RemoteSummary[] = [];
      let pers = false;
      try {
        const r = await fetch(p("/api/conversations"), { credentials: "include" });
        if (r.ok) {
          const j = (await r.json()) as {
            serverPersistence?: boolean;
            conversations?: RemoteSummary[];
          };
          pers = j.serverPersistence === true;
          remote = j.conversations ?? [];
        }
      } catch {
        /* offline */
      }
      if (cancelled) return;
      setServerPersistence(pers);
      let merged = mergeRemoteAndLocal(remote, local);
      if (merged.length === 0) {
        const id = crypto.randomUUID();
        const now = new Date().toISOString();
        const empty: ChatThreadState = {
          id,
          title: "New chat",
          updatedAt: now,
          messages: [],
          remote: false,
          hydrated: true,
          hydrateVersion: 1,
        };
        setThreads([empty]);
        setActiveId(id);
        saveLocalThreads(userId, [empty]);
        setReady(true);
        return;
      }

      // Auto-select does not go through openThread — hydrate the first remote
      // thread before the composer mounts, or a send would PUT [] and wipe history.
      const initial = merged[0]!;
      if (initial.remote && !initial.hydrated) {
        const body = await fetchConversationBody(initial.id);
        if (cancelled) return;
        if (body) {
          merged = merged.map((x) =>
            x.id === initial.id ? withHydratedConversation(x, body) : x,
          );
        }
      }
      if (cancelled) return;
      setThreads(merged);
      setActiveId(merged[0]?.id ?? null);
      setReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [userId]);

  const activeThread = threads.find((t) => t.id === activeId) ?? null;

  const openThread = useCallback(
    async (id: string) => {
      const t = threads.find((x) => x.id === id);
      if (t?.remote && !t.hydrated) {
        const body = await fetchConversationBody(id);
        if (body) {
          setThreads((prev) =>
            prev.map((x) => (x.id === id ? withHydratedConversation(x, body) : x)),
          );
        }
      }
      setActiveId(id);
      setByokMode(false);
      setRenamingId(null);
    },
    [threads],
  );

  const newChat = useCallback(() => {
    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    const t: ChatThreadState = {
      id,
      title: "New chat",
      updatedAt: now,
      messages: [],
      remote: false,
      hydrated: true,
      hydrateVersion: 1,
    };
    setThreads((prev) => {
      const next = [t, ...prev];
      saveLocalThreads(userId, next);
      return next;
    });
    setActiveId(id);
    setByokMode(false);
    setRenamingId(null);
  }, [userId]);

  const deleteThread = useCallback(
    async (id: string) => {
      const t = threadsRef.current.find((x) => x.id === id);
      if (t?.remote && serverPersistence) {
        try {
          await fetch(p(`/api/conversations/${id}`), { method: "DELETE", credentials: "include" });
        } catch {
          /* ignore */
        }
      }
      setThreads((prev) => {
        const filtered = prev.filter((x) => x.id !== id);
        const next =
          filtered.length === 0
            ? [
                {
                  id: crypto.randomUUID(),
                  title: "New chat",
                  updatedAt: new Date().toISOString(),
                  messages: [] as UIMessage[],
                  remote: false,
                  hydrated: true,
                  hydrateVersion: 1,
                } satisfies ChatThreadState,
              ]
            : filtered;
        saveLocalThreads(userId, next);
        queueMicrotask(() => {
          setActiveId((cur) => (cur === id ? next[0]!.id : cur));
        });
        return next;
      });
      setRenamingId(null);
    },
    [serverPersistence, userId],
  );

  const renameThread = useCallback(
    (id: string, title: string) => {
      const trimmed = title.trim();
      if (!trimmed) return;
      setThreads((prev) => {
        const next = prev.map((x) =>
          x.id === id ? { ...x, title: trimmed, updatedAt: new Date().toISOString() } : x,
        );
        saveLocalThreads(userId, next);
        return next;
      });
      scheduleServerSave(id);
    },
    [userId, scheduleServerSave],
  );

  const cancelRename = useCallback(() => {
    renameHandledRef.current = true;
    setRenamingId(null);
  }, []);
  const commitRename = useCallback(
    (id: string, currentTitle: string, draft: string) => {
      renameHandledRef.current = true;
      const next = draft.trim();
      // Dirty check: equal/empty drafts close without a write (no reorder,
      // no PUT for a no-op).
      if (next && next !== currentTitle) renameThread(id, next);
      setRenamingId(null);
    },
    [renameThread],
  );

  const clearActiveThread = useCallback(() => {
    if (!activeId) return;
    const cur = threadsRef.current.find((x) => x.id === activeId);
    // Do not clear+PUT an unhydrated remote thread — that would wipe server history.
    if (cur && !canFlushServerMessages(cur)) return;
    allowTruncateRef.current[activeId] = true;
    setThreads((prev) => {
      const next = prev.map((t) =>
        t.id === activeId
          ? {
              ...t,
              messages: [],
              updatedAt: new Date().toISOString(),
              hydrateVersion: t.hydrateVersion + 1,
              hydrated: true,
            }
          : t,
      );
      saveLocalThreads(userId, next);
      return next;
    });
    scheduleServerSave(activeId);
  }, [activeId, userId, scheduleServerSave]);

  const allowTruncateForThread = useCallback((threadId: string) => {
    allowTruncateRef.current[threadId] = true;
  }, []);

  const onMessagesCommit = useCallback(
    (threadId: string, messages: UIMessage[]) => {
      const cur = threadsRef.current.find((x) => x.id === threadId);
      // Never mark an unhydrated remote thread hydrated from a partial client
      // array — that would unlock flushServerSave and erase Postgres history.
      if (cur && !canFlushServerMessages(cur)) return;
      setThreads((prev) => {
        const next = prev.map((t) =>
          t.id === threadId
            ? { ...t, messages, updatedAt: new Date().toISOString(), hydrated: true }
            : t,
        );
        saveLocalThreads(userId, next);
        return next;
      });
      scheduleServerSave(threadId);
    },
    [userId, scheduleServerSave],
  );

  const onTitleDerived = useCallback(
    (threadId: string, title: string) => {
      setThreads((prev) => {
        const next = prev.map((t) =>
          t.id === threadId && (t.title === "New chat" || !t.title.trim())
            ? { ...t, title, updatedAt: new Date().toISOString() }
            : t,
        );
        saveLocalThreads(userId, next);
        return next;
      });
      scheduleServerSave(threadId);
    },
    [userId, scheduleServerSave],
  );

  // Cmd+/ toggles sidebar; Esc closes BYOK configure mode.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && e.key === "/") {
        const active = document.activeElement;
        if (
          active instanceof HTMLInputElement ||
          active instanceof HTMLTextAreaElement ||
          (active instanceof HTMLElement && active.isContentEditable)
        ) {
          return;
        }
        e.preventDefault();
        setCollapsed((v) => !v);
      } else if (e.key === "Escape" && byokMode) {
        e.preventDefault();
        setByokMode(false);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [byokMode]);

  const grouped = useMemo(
    () => groupThreadsByDate(filterThreadsByQuery(threads, threadQuery)),
    [threads, threadQuery],
  );
  const subtitle = userEmail ?? displayName ?? userId ?? "Signed in";

  if (!ready || !activeThread) {
    return (
      <div className="flex min-h-dvh items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }

  return (
    <div className={cn("app-shell", collapsed && "app-shell-sidebar-collapsed")}>
      <aside className="app-sidebar" aria-label="App sidebar" data-expanded={!collapsed}>
        <div className="app-sidebar-body">
          <div className="dc-sidebar-brand">
            <div className="dc-sidebar-brand-mark">DT</div>
            <div>
              <div className="dc-sidebar-brand-name">digichat</div>
              <div className="dc-sidebar-brand-version">v0.1 · digithings</div>
            </div>
          </div>

          <button type="button" className="dc-sidebar-newchat" onClick={newChat}>
            + new chat
          </button>

          <label className="dc-sidebar-search">
            <span className="sr-only">Search conversations</span>
            <input
              type="search"
              value={threadQuery}
              onChange={(e) => setThreadQuery(e.target.value)}
              placeholder="Search chats…"
              autoComplete="off"
              spellCheck={false}
            />
          </label>

          {grouped.length === 0 ? (
            <p className="dc-sidebar-empty" role="status">
              {threadQuery.trim() ? "No chats match that search." : "No chats yet."}
            </p>
          ) : (
            grouped.map((g) => (
              <section key={g.label} className="app-sidebar-section">
                <h3>{g.label}</h3>
                <ul>
                  {g.items.map((t) => (
                    <li key={t.id} style={{ padding: 0 }}>
                      <div
                        className={cn("dc-sidebar-thread", t.id === activeId && "is-active")}
                        onClick={() => void openThread(t.id)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            void openThread(t.id);
                          }
                        }}
                        role="button"
                        tabIndex={0}
                        aria-pressed={t.id === activeId}
                      >
                        <span className="dc-sidebar-thread-title">
                          {renamingId === t.id ? (
                            <input
                              className="dc-sidebar-rename"
                              value={renameDraft}
                              ref={(el) => {
                                // No autoFocus: it scroll-jumps the sidebar.
                                // Focus without scrolling once mounted.
                                if (el && renamingId === t.id) el.focus({ preventScroll: true });
                              }}
                              maxLength={120}
                              aria-label="Rename chat"
                              onClick={(e) => e.stopPropagation()}
                              onKeyDown={(e) => {
                                e.stopPropagation();
                                if (e.key === "Enter") {
                                  e.preventDefault();
                                  commitRename(t.id, t.title, renameDraft);
                                } else if (e.key === "Escape") {
                                  e.preventDefault();
                                  cancelRename();
                                }
                              }}
                              onChange={(e) => setRenameDraft(e.target.value)}
                              onBlur={() => {
                                // Blur after Enter/Escape already resolved, or a
                                // no-op draft: close without writing.
                                if (renameHandledRef.current) return;
                                commitRename(t.id, t.title, renameDraft);
                              }}
                            />
                          ) : (
                            t.title
                          )}
                        </span>
                        <span className="dc-sidebar-thread-time">{formatTimestamp(t.updatedAt)}</span>
                        <DropdownMenu>
                          <DropdownMenuTrigger
                            aria-label={`Actions for ${t.title}`}
                            onClick={(e) => e.stopPropagation()}
                            onKeyDown={(e) => e.stopPropagation()}
                            className="text-muted-foreground hover:text-foreground"
                          >
                            <MoreHorizontal className="size-3.5" />
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-44">
                            <DropdownMenuItem
                              onClick={() => {
                                renameHandledRef.current = false;
                                setRenamingId(t.id);
                                setRenameDraft(t.title);
                              }}
                            >
                              <Pencil className="size-3.5" />
                              Rename
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              className="text-destructive focus:text-destructive"
                              onClick={() => void deleteThread(t.id)}
                            >
                              <Trash2 className="size-3.5" />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            ))
          )}

          <section className="app-sidebar-section">
            <h3>Commands</h3>
            <ul>
              {SLASH_REFERENCE.map((c) => (
                <li key={c.cmd} className="dc-sidebar-cmd">
                  <span className="dc-sidebar-cmd-key">{c.cmd}</span>
                  <span>{c.hint}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="app-sidebar-section">
            <Link
              href="https://digithings.ai"
              target="_blank"
              rel="noreferrer"
              className="dc-sidebar-cmd"
            >
              <span>digithings.ai</span>
              <span aria-hidden>↗</span>
            </Link>
            <button
              type="button"
              className="dc-sidebar-cmd"
              style={{ width: "100%", background: "transparent", border: "none", cursor: "pointer" }}
              onClick={() => signOut({ callbackUrl: p("/embed") })}
            >
              <span>sign out</span>
              <span aria-hidden>⏻</span>
            </button>
          </section>
        </div>
      </aside>

      <div className="app-shell-main-col">
        <header className="app-topbar">
          <span className="app-topbar-title">{activeThread.title || "New chat"}</span>
          <span className="app-topbar-meta">
            <button
              type="button"
              onClick={() => setByokMode(true)}
              className="underline-offset-2 hover:underline"
              style={{ background: "transparent", border: "none", color: "inherit", cursor: "pointer", fontFamily: "inherit", fontSize: "inherit" }}
              aria-label="Configure bring your own key"
            >
              bring your own key
            </button>
            {" · "}
            {subtitle} · <button
              type="button"
              onClick={() => setCollapsed((v) => !v)}
              className="underline-offset-2 hover:underline"
              style={{ background: "transparent", border: "none", color: "inherit", cursor: "pointer", fontFamily: "inherit", fontSize: "inherit" }}
              aria-label="Toggle sidebar"
            >
              ⌘/
            </button>
          </span>
        </header>

        <main className="app-main">
          {activeThread.remote && !activeThread.hydrated ? (
            <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
              <p>Could not load this conversation yet.</p>
              <button
                type="button"
                className="underline-offset-2 hover:underline"
                style={{
                  background: "transparent",
                  border: "none",
                  color: "inherit",
                  cursor: "pointer",
                  fontFamily: "inherit",
                  fontSize: "inherit",
                }}
                onClick={() => void openThread(activeThread.id)}
              >
                Retry
              </button>
            </div>
          ) : (
            <ChatPanel
              key={`${activeThread.id}-${activeThread.hydrateVersion}`}
              threadId={activeThread.id}
              threadTitle={activeThread.title}
              initialMessages={activeThread.messages}
              onMessagesCommit={onMessagesCommit}
              onTitleDerived={onTitleDerived}
              onAllowTruncate={allowTruncateForThread}
              byokMode={byokMode}
              onByokModeChange={setByokMode}
              onSlashCommand={(cmd) => {
                const [name] = cmd.trim().split(/\s+/);
                if (name === "/clear") {
                  clearActiveThread();
                  return true;
                }
                if (name === "/history") {
                  setCollapsed(false);
                  const first = document.querySelector<HTMLElement>(".dc-sidebar-thread");
                  first?.focus();
                  return true;
                }
                return false;
              }}
            />
          )}
        </main>
      </div>
    </div>
  );
}
