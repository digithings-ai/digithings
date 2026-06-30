"use client";

/**
 * ChatShell — authenticated chat chrome for DigiChat.
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
  loadLocalThreads,
  mergeRemoteAndLocal,
  saveLocalThreads,
  type ChatThreadState,
} from "@/lib/thread-local";
import { cn } from "@/lib/utils";
import { p } from "@/lib/base-path";

type RemoteSummary = { id: string; title: string; updatedAt: string };

const SLASH_REFERENCE: Array<{ cmd: string; hint: string }> = [
  { cmd: "/help", hint: "list commands" },
  { cmd: "/key", hint: "BYOK (CLI)" },
  { cmd: "/model", hint: "<id>" },
  { cmd: "/clear", hint: "clear thread" },
  { cmd: "/scope", hint: "show JWT scopes" },
  { cmd: "/history", hint: "focus sidebar" },
  { cmd: "/settings", hint: "alias for /key" },
];

function groupByDate(threads: ChatThreadState[]): Array<{ label: string; items: ChatThreadState[] }> {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = todayStart - 24 * 60 * 60 * 1000;
  const weekStart = todayStart - 7 * 24 * 60 * 60 * 1000;
  const buckets: Record<string, ChatThreadState[]> = { Today: [], Yesterday: [], "This week": [], Older: [] };
  for (const t of threads) {
    const ts = Date.parse(t.updatedAt);
    if (Number.isNaN(ts) || ts >= todayStart) buckets.Today!.push(t);
    else if (ts >= yesterdayStart) buckets.Yesterday!.push(t);
    else if (ts >= weekStart) buckets["This week"]!.push(t);
    else buckets.Older!.push(t);
  }
  return Object.entries(buckets)
    .filter(([, v]) => v.length > 0)
    .map(([label, items]) => ({ label, items }));
}

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

  const threadsRef = useRef(threads);
  useEffect(() => {
    threadsRef.current = threads;
  }, [threads]);

  const debouncedSaveRef = useRef<Record<string, ReturnType<typeof setTimeout> | undefined>>({});

  const flushServerSave = useCallback(
    async (threadId: string) => {
      if (!serverPersistence) return;
      let t = threadsRef.current.find((x) => x.id === threadId);
      if (!t) return;

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
      await fetch(p(`/api/conversations/${threadId}`), {
        method: "PUT",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ title: snap.title, messages: snap.messages }),
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
      const merged = mergeRemoteAndLocal(remote, local);
      setThreads(merged);
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
      } else {
        setActiveId(merged[0]?.id ?? null);
      }
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
        try {
          const r = await fetch(p(`/api/conversations/${id}`), { credentials: "include" });
          if (r.ok) {
            const j = (await r.json()) as { title: string; messages: UIMessage[] };
            setThreads((prev) =>
              prev.map((x) =>
                x.id === id
                  ? {
                      ...x,
                      title: j.title,
                      messages: j.messages,
                      hydrated: true,
                      hydrateVersion: x.hydrateVersion + 1,
                    }
                  : x,
              ),
            );
          }
        } catch {
          /* ignore */
        }
      }
      setActiveId(id);
      setByokMode(false);
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

  const clearActiveThread = useCallback(() => {
    if (!activeId) return;
    setThreads((prev) => {
      const next = prev.map((t) =>
        t.id === activeId
          ? { ...t, messages: [], updatedAt: new Date().toISOString(), hydrateVersion: t.hydrateVersion + 1 }
          : t,
      );
      saveLocalThreads(userId, next);
      return next;
    });
    scheduleServerSave(activeId);
  }, [activeId, userId, scheduleServerSave]);

  const onMessagesCommit = useCallback(
    (threadId: string, messages: UIMessage[]) => {
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

  const grouped = useMemo(() => groupByDate(threads), [threads]);
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
              <div className="dc-sidebar-brand-name">DigiChat</div>
              <div className="dc-sidebar-brand-version">v0.1 · digithings</div>
            </div>
          </div>

          <button type="button" className="dc-sidebar-newchat" onClick={newChat}>
            + new chat
          </button>

          {grouped.map((g) => (
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
                      <span className="dc-sidebar-thread-title">{t.title}</span>
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
                              const next = window.prompt("Rename chat", t.title);
                              if (next != null) renameThread(t.id, next);
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
          ))}

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
              onClick={() => signOut({ callbackUrl: p("/login") })}
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
          <ChatPanel
            key={`${activeThread.id}-${activeThread.hydrateVersion}`}
            threadId={activeThread.id}
            threadTitle={activeThread.title}
            initialMessages={activeThread.messages}
            onMessagesCommit={onMessagesCommit}
            onTitleDerived={onTitleDerived}
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
        </main>
      </div>
    </div>
  );
}
