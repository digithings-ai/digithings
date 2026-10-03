"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AssistantRuntimeProvider, useExternalStoreRuntime } from "@assistant-ui/react";
import { useMotionSafe } from "@digithings/ui";
import { DigichatThread } from "@digithings/ui/chat/thread";
import { DigichatThreadList } from "@digithings/ui/chat/thread-list";
import {
  EXAMPLES,
  doneCursor,
  exampleById,
  isExampleId,
  openCursor,
  projectTurns,
  shouldTakeOver,
  stepTour,
  type ExampleId,
  type PlayCursor,
  type TourState,
} from "@/app/_strategy-script";
import { digichatFont } from "@/components/chat/digichat-font";
import { OpenToolFallback } from "@/components/chat/open-tool-fallback";

/** Hides the real composer. The visitor picks an example; they do not type into one. */
export const COMPOSER_HIDDEN = "[&_.aui-composer-root]:hidden";

const THREADS = EXAMPLES.map((example) => ({
  status: "regular" as const,
  id: example.id,
  title: example.title,
}));

function isControl(target: EventTarget | null): boolean {
  return target instanceof Element
    && Boolean(target.closest("button, a, input, textarea, summary, [role='button']"));
}

/**
 * The digichat session UI: `DigichatThread` plus `DigichatThreadList` from
 * `@digithings/ui` (the same thread and sidebar digichat mounts). The frame
 * carries `data-thread-skin="digichat"` and Geist Mono, matching the digichat
 * host. apps/digichat is not imported — that app is not a dependency of this
 * Next app.
 *
 * Server render and reduced motion show the first example in full. With
 * motion, once the frame is in view the tour streams every sidebar chat.
 * A click, a key, a wheel, or a hover on a control stops the tour and shows
 * the current chat in full. Choosing a header loads that example in full.
 */
export function ScriptedDigichatSession() {
  const frameRef = useRef<HTMLDivElement>(null);
  const heldRef = useRef(false);
  const timerRef = useRef(0);
  const activeRef = useRef<ExampleId>(EXAMPLES[0].id);
  const motion = useMotionSafe();
  const [activeId, setActiveId] = useState<ExampleId>(EXAMPLES[0].id);
  const [cursor, setCursor] = useState<PlayCursor>(() => doneCursor(EXAMPLES[0].turns));
  const example = exampleById(activeId);
  const view = useMemo(() => projectTurns(example.turns, cursor), [example, cursor]);

  const takeOver = useCallback((id?: string) => {
    window.clearTimeout(timerRef.current);
    const next = isExampleId(id) ? id : activeRef.current;
    if (heldRef.current && next === activeRef.current) return;
    heldRef.current = true;
    activeRef.current = next;
    setActiveId(next);
    setCursor(doneCursor(exampleById(next).turns));
  }, []);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    const onEvent = (event: Event) => {
      if (!shouldTakeOver({ isTrusted: event.isTrusted, type: event.type, control: isControl(event.target) })) {
        return;
      }
      takeOver();
    };
    frame.addEventListener("pointerdown", onEvent, true);
    frame.addEventListener("pointerover", onEvent, true);
    frame.addEventListener("wheel", onEvent, true);
    frame.addEventListener("keydown", onEvent, true);
    return () => {
      frame.removeEventListener("pointerdown", onEvent, true);
      frame.removeEventListener("pointerover", onEvent, true);
      frame.removeEventListener("wheel", onEvent, true);
      frame.removeEventListener("keydown", onEvent, true);
    };
  }, [takeOver]);

  useEffect(() => {
    if (!motion || typeof IntersectionObserver === "undefined") return;
    const frame = frameRef.current;
    if (!frame) return;

    let stopped = false;
    let current: TourState = { id: EXAMPLES[0].id, cursor: openCursor() };

    const step = () => {
      if (stopped || heldRef.current) return;
      const next = stepTour(current);
      current = next.state;
      activeRef.current = current.id;
      setActiveId(current.id);
      setCursor(current.cursor);
      timerRef.current = window.setTimeout(step, next.delay);
    };

    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        io.disconnect();
        if (stopped || heldRef.current) return;
        current = { id: EXAMPLES[0].id, cursor: openCursor() };
        activeRef.current = current.id;
        setActiveId(current.id);
        setCursor(current.cursor);
        timerRef.current = window.setTimeout(step, 280);
      },
      { threshold: 0.35 },
    );
    io.observe(frame);
    return () => {
      stopped = true;
      io.disconnect();
      window.clearTimeout(timerRef.current);
    };
  }, [motion]);

  const runtime = useExternalStoreRuntime({
    messages: view.messages,
    isRunning: view.running,
    isDisabled: true,
    convertMessage: (message) => message,
    onNew: async () => {},
    adapters: {
      threadList: {
        threadId: activeId,
        threads: THREADS,
        onSwitchToNewThread: () => takeOver(),
        onSwitchToThread: (threadId: string) => takeOver(threadId),
      },
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div
        ref={frameRef}
        data-thread-skin="digichat"
        aria-label="digichat"
        className={`${digichatFont.variable} ${digichatFont.className} grid h-[min(36rem,calc(100svh-16rem))] min-h-[24rem] grid-rows-[auto_minmax(0,1fr)] overflow-hidden border border-hair md:grid-cols-[14rem_minmax(0,1fr)] md:grid-rows-1`}
      >
        <div className="max-h-40 min-h-0 overflow-hidden md:flex md:max-h-none">
          <DigichatThreadList className="h-full w-full" />
        </div>
        <DigichatThread
          welcome=""
          placeholder=""
          toolCallsMode="expanded"
          reasoningMode="off"
          components={{ ToolFallback: OpenToolFallback }}
          className={`h-full min-h-0 ${COMPOSER_HIDDEN}`}
        />
      </div>
    </AssistantRuntimeProvider>
  );
}
