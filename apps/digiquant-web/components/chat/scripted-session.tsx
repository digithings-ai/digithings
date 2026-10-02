"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AssistantRuntimeProvider, useExternalStoreRuntime } from "@assistant-ui/react";
import { useMotionSafe } from "@digithings/ui";
import { DigichatThread } from "@digithings/ui/chat/thread";
import { DigichatThreadList } from "@digithings/ui/chat/thread-list";
import {
  nextCursor,
  PLAY_DONE,
  PLAY_START,
  project,
  STRATEGY_THREAD_ID,
  STRATEGY_THREAD_TITLE,
  type PlayCursor,
} from "@/app/_strategy-script";
import { OpenToolFallback } from "@/components/chat/open-tool-fallback";

/** Hides the real composer. The visitor does not type; the script plays itself. */
export const COMPOSER_HIDDEN = "[&_.aui-composer-root]:hidden";

/**
 * The digichat session UI: `DigichatThread` plus `DigichatThreadList` from
 * `@digithings/ui` (the same thread and sidebar digichat mounts). apps/digichat
 * is not imported — that app is not a dependency of this Next app.
 *
 * Server render and reduced motion show the finished script. With motion, the
 * script plays once the frame is in view: assistant text streams, then each
 * tool call in the chain runs and settles through the thread's own tool rows.
 */
export function ScriptedDigichatSession() {
  const frameRef = useRef<HTMLDivElement>(null);
  const motion = useMotionSafe();
  const [replay, setReplay] = useState(0);
  const [cursor, setCursor] = useState<PlayCursor>(PLAY_DONE);
  const view = useMemo(() => project(cursor), [cursor]);

  useEffect(() => {
    if (!motion || typeof IntersectionObserver === "undefined") {
      const reset = window.setTimeout(() => setCursor(PLAY_DONE), 0);
      return () => window.clearTimeout(reset);
    }
    const frame = frameRef.current;
    if (!frame) return;

    let stopped = false;
    let timer = 0;
    let current = PLAY_START;

    const step = () => {
      if (stopped) return;
      const next = nextCursor(current);
      current = next.cursor;
      setCursor(current);
      if (!next.done) timer = window.setTimeout(step, next.delay);
    };

    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        io.disconnect();
        current = PLAY_START;
        setCursor(PLAY_START);
        timer = window.setTimeout(step, 280);
      },
      { threshold: 0.35 },
    );
    io.observe(frame);
    return () => {
      stopped = true;
      io.disconnect();
      window.clearTimeout(timer);
    };
  }, [motion, replay]);

  const runtime = useExternalStoreRuntime({
    messages: view.messages,
    isRunning: view.running,
    isDisabled: true,
    convertMessage: (message) => message,
    onNew: async () => {},
    adapters: {
      threadList: {
        threadId: STRATEGY_THREAD_ID,
        threads: [
          { status: "regular", id: STRATEGY_THREAD_ID, title: STRATEGY_THREAD_TITLE },
        ],
        onSwitchToNewThread: () => setReplay((n) => n + 1),
      },
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div
        ref={frameRef}
        aria-label="Scripted strategy-building story"
        className="grid h-[min(36rem,calc(100svh-16rem))] min-h-[24rem] overflow-hidden border border-hair md:grid-cols-[14rem_minmax(0,1fr)]"
      >
        <div className="hidden min-h-0 md:flex">
          <DigichatThreadList className="h-full w-full" />
        </div>
        <DigichatThread
          welcome=""
          placeholder=""
          toolCallsMode="expanded"
          reasoningMode="off"
          components={{ ToolFallback: OpenToolFallback }}
          className={`scripted-digichat h-full min-h-0 ${COMPOSER_HIDDEN}`}
        />
      </div>
    </AssistantRuntimeProvider>
  );
}
