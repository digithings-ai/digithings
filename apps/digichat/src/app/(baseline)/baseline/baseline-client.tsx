"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { AssistantChatTransport, useChatRuntime } from "@assistant-ui/ai-sdk";
import { ThreadSkinView } from "@/components/assistant-ui/skins";
import { p } from "@/lib/base-path";
import { cn } from "@/lib/utils";
import { parseThreadSkin, THREAD_SKINS } from "@/lib/thread-skins";

/**
 * Official assistant-ui templates (the 11 catalog ids) plus first-party
 * `digichat`. Transport is the localhost baseline BFF, which proxies production
 * digithings.ai/api/chat (Cloudflare stack).
 *
 * `?skin=base|chatgpt|claude|grok|gemini|perplexity|react-ink|expo-react-native|base-assistant-ui|webpage-assistant|product-page-assistant|digichat`
 * `?theme=dark|light`
 */
export function BaselineClient() {
  return (
    <Suspense fallback={null}>
      <BaselineClientInner />
    </Suspense>
  );
}

function BaselineClientInner() {
  const searchParams = useSearchParams();
  const skin = parseThreadSkin(searchParams.get("skin"));
  const theme = searchParams.get("theme") === "dark" ? "dark" : "light";

  const runtime = useChatRuntime({
    transport: new AssistantChatTransport({
      api: p("/api/baseline-chat"),
      prepareSendMessagesRequest: ({ messages, body, headers }) => {
        const h = new Headers(headers as HeadersInit | undefined);
        h.set("X-Digi-Run-Id", crypto.randomUUID());
        return {
          body: {
            ...(typeof body === "object" && body !== null ? body : {}),
            messages,
          },
          headers: h,
        };
      },
    }),
  });

  const hrefFor = (nextSkin: string, nextTheme: string) => {
    const qs = new URLSearchParams();
    if (nextSkin !== "base") qs.set("skin", nextSkin);
    if (nextTheme === "dark") qs.set("theme", "dark");
    const query = qs.toString();
    return query ? `/baseline?${query}` : "/baseline";
  };

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className={cn("flex h-dvh flex-col", theme === "dark" && "dark")}>
        <nav
          aria-label="assistant-ui templates"
          className="flex shrink-0 flex-wrap items-center gap-1 border-b border-zinc-200 bg-white px-3 py-2 text-xs text-zinc-600 dark:border-zinc-800 dark:bg-black dark:text-zinc-400"
        >
          {THREAD_SKINS.map((id) => {
            const href = hrefFor(id, theme);
            const active = skin === id;
            return (
              <a
                key={id}
                href={href}
                className={cn(
                  "rounded-md px-2 py-1 hover:bg-zinc-100 dark:hover:bg-zinc-900",
                  active && "bg-zinc-100 font-medium text-zinc-900 dark:bg-zinc-900 dark:text-zinc-100",
                )}
              >
                {id}
              </a>
            );
          })}
          <a
            href={hrefFor(skin, theme === "dark" ? "light" : "dark")}
            className="ml-auto rounded-md px-2 py-1 hover:bg-zinc-100 dark:hover:bg-zinc-900"
          >
            {theme === "dark" ? "light" : "dark"}
          </a>
        </nav>
        <div className="min-h-0 flex-1 bg-background text-foreground">
          <ThreadSkinView skin={skin} />
        </div>
      </div>
    </AssistantRuntimeProvider>
  );
}
