"use client";

import { Thread } from "@/app/(vanilla)/stock/thread.aui";
import { useComposerCopy } from "@/components/stock/skin-chrome";

/**
 * Web facsimile of the official Expo React Native Assistant.
 * The native starter is vendored at
 * `reference/assistant-ui-templates/expo-react-native` and is not imported
 * by Next.js (`react-native` / Expo stay out of the web bundle).
 */
export function ExpoReactNative() {
  const { title } = useComposerCopy("How can I help you today?", "Send a message...");
  return (
    <div className="flex h-full items-center justify-center bg-zinc-200 p-4">
      <div className="flex h-[min(740px,100%)] w-[min(390px,100%)] flex-col overflow-hidden rounded-[2rem] border border-zinc-300 bg-white shadow-2xl">
        <header className="flex shrink-0 items-center justify-between border-b border-zinc-200 px-4 py-3">
          <div className="text-sm font-semibold tracking-tight">
            {title || "assistant-ui"}
          </div>
          <div className="text-xs text-zinc-500">Expo</div>
        </header>
        <div className="min-h-0 flex-1 bg-white">
          <Thread />
        </div>
      </div>
    </div>
  );
}
