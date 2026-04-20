"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { MessageSquarePlus, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import type { UIMessage } from "ai";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarSeparator,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { ChatChrome, ChatPanel } from "@/components/chat-panel";
import {
  loadLocalThreads,
  mergeRemoteAndLocal,
  saveLocalThreads,
  type ChatThreadState,
} from "@/lib/thread-local";
import { cn } from "@/lib/utils";

type RemoteSummary = { id: string; title: string; updatedAt: string };

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

  const threadsRef = useRef(threads);
  useEffect(() => {
    threadsRef.current = threads;
  }, [threads]);

  const debouncedSaveRef = useRef<
    Record<string, ReturnType<typeof setTimeout> | undefined>
  >({});

  const flushServerSave = useCallback(
    async (threadId: string) => {
      if (!serverPersistence) return;
      let t = threadsRef.current.find((x) => x.id === threadId);
      if (!t) return;

      if (!t.remote) {
        const cr = await fetch("/api/conversations", {
          method: "POST",
          credentials: "include",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ id: t.id, title: t.title }),
        });
        if (!cr.ok) return;
        setThreads((prev) =>
          prev.map((x) => (x.id === threadId ? { ...x, remote: true } : x))
        );
        t = { ...t, remote: true };
      }

      const snap = threadsRef.current.find((x) => x.id === threadId) ?? t;
      await fetch(`/api/conversations/${threadId}`, {
        method: "PUT",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          title: snap.title,
          messages: snap.messages,
        }),
      });
    },
    [serverPersistence]
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
    [flushServerSave, serverPersistence]
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const local = loadLocalThreads(userId);
      let remote: RemoteSummary[] = [];
      let pers = false;
      try {
        const r = await fetch("/api/conversations", { credentials: "include" });
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
          const r = await fetch(`/api/conversations/${id}`, {
            credentials: "include",
          });
          if (r.ok) {
            const j = (await r.json()) as {
              title: string;
              messages: UIMessage[];
            };
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
                  : x
              )
            );
          }
        } catch {
          /* ignore */
        }
      }
      setActiveId(id);
    },
    [threads]
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
  }, [userId]);

  const deleteThread = useCallback(
    async (id: string) => {
      const t = threadsRef.current.find((x) => x.id === id);
      if (t?.remote && serverPersistence) {
        try {
          await fetch(`/api/conversations/${id}`, {
            method: "DELETE",
            credentials: "include",
          });
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
          setActiveId((cur) =>
            cur === id ? next[0]!.id : cur
          );
        });
        return next;
      });
    },
    [serverPersistence, userId]
  );

  const renameThread = useCallback((id: string, title: string) => {
    const trimmed = title.trim();
    if (!trimmed) return;
    setThreads((prev) => {
      const next = prev.map((x) =>
        x.id === id
          ? { ...x, title: trimmed, updatedAt: new Date().toISOString() }
          : x
      );
      saveLocalThreads(userId, next);
      return next;
    });
    scheduleServerSave(id);
  }, [userId, scheduleServerSave]);

  const onMessagesCommit = useCallback(
    (threadId: string, messages: UIMessage[]) => {
      setThreads((prev) => {
        const next = prev.map((t) =>
          t.id === threadId
            ? {
                ...t,
                messages,
                updatedAt: new Date().toISOString(),
                hydrated: true,
              }
            : t
        );
        saveLocalThreads(userId, next);
        return next;
      });
      scheduleServerSave(threadId);
    },
    [userId, scheduleServerSave]
  );

  const onTitleDerived = useCallback((threadId: string, title: string) => {
    setThreads((prev) => {
      const next = prev.map((t) =>
        t.id === threadId && (t.title === "New chat" || !t.title.trim())
          ? { ...t, title, updatedAt: new Date().toISOString() }
          : t
      );
      saveLocalThreads(userId, next);
      return next;
    });
    scheduleServerSave(threadId);
  }, [userId, scheduleServerSave]);

  const subtitle =
    userEmail ?? displayName ?? userId ?? "Signed in";

  if (!ready || !activeThread) {
    return (
      <div className="flex min-h-dvh items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }

  return (
    <SidebarProvider defaultOpen className="min-h-dvh">
      <Sidebar collapsible="icon" className="border-r border-sidebar-border">
        <SidebarHeader className="gap-2 border-b border-sidebar-border px-2 py-3">
          <div className="flex items-center gap-2 px-1 group-data-[collapsible=icon]:justify-center">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-muted/40 text-xs font-bold text-foreground">
              DT
            </div>
            <div className="min-w-0 flex-1 group-data-[collapsible=icon]:hidden">
              <p className="truncate text-sm font-semibold tracking-tight text-sidebar-foreground">
                DigiChat
              </p>
              <p className="truncate text-xs text-muted-foreground">digithings</p>
            </div>
          </div>
          <Button
            type="button"
            size="sm"
            className="w-full justify-start gap-2 group-data-[collapsible=icon]:size-8 group-data-[collapsible=icon]:p-0"
            onClick={newChat}
            aria-label="New chat"
          >
            <MessageSquarePlus className="size-4 shrink-0" />
            <span className="group-data-[collapsible=icon]:hidden">New chat</span>
          </Button>
        </SidebarHeader>
        <SidebarContent className="gap-0">
          <SidebarGroup className="py-2">
            <SidebarGroupLabel className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Conversations
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {threads.map((t) => (
                  <SidebarMenuItem key={t.id}>
                    <SidebarMenuButton
                      isActive={t.id === activeId}
                      className="pr-8"
                      onClick={() => void openThread(t.id)}
                    >
                      <span className="truncate text-left">{t.title}</span>
                    </SidebarMenuButton>
                    <DropdownMenu>
                      <DropdownMenuTrigger
                        className={cn(
                          "absolute top-1 right-1 flex size-6 items-center justify-center rounded-md text-sidebar-foreground opacity-80 hover:bg-sidebar-accent hover:opacity-100 focus-visible:ring-2 focus-visible:ring-sidebar-ring group-data-[collapsible=icon]:hidden"
                        )}
                        aria-label={`Actions for ${t.title}`}
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
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarSeparator />
        <SidebarFooter className="gap-2 p-2 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
          <Link
            href="https://digithings.ai"
            target="_blank"
            rel="noreferrer"
            className="block truncate px-2 py-1 hover:text-sidebar-foreground"
          >
            digithings.ai
          </Link>
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>
      <SidebarInset className="flex min-h-dvh min-w-0 flex-1 flex-col bg-background">
        <div className="flex min-h-0 flex-1 flex-col px-3 pb-4 pt-2 md:px-5">
          <ChatChrome
            leading={
              <SidebarTrigger className="shrink-0 md:flex [&>svg]:size-4" />
            }
            threadTitle={activeThread.title}
            userSubtitle={subtitle}
          />
          <div className="mt-2 flex min-h-0 flex-1 flex-col">
            <ChatPanel
              key={`${activeThread.id}-${activeThread.hydrateVersion}`}
              threadId={activeThread.id}
              threadTitle={activeThread.title}
              initialMessages={activeThread.messages}
              onMessagesCommit={onMessagesCommit}
              onTitleDerived={onTitleDerived}
            />
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
