"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@digithings/ui/ui";
import {
  DESK_EMBED_SRC,
  DESK_EMPTY_COPY,
  DESK_YIELD_LABEL,
  OPEN_BUDGET_MS,
  WALK_DWELL_MS,
  activateNavLink,
  bindYieldListeners,
  dashboardReady,
  deskStatus,
  embedLooksDown,
  nextWalkAnchor,
  probeEmbed,
  shouldYieldToUser,
  type DeskPhase,
} from "./desk-walk";

/** The product frame: the terminal, same-origin in dev so a walkthrough can click its sidebar.
 *  A trusted pointer, wheel, or key inside the frame stops the walk. Take control does too. */
export function EmbeddedDesk() {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const yieldRef = useRef<() => void>(() => {});
  const [phase, setPhase] = useState<DeskPhase>("opening");

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;

    let stopped = false;
    let yielded = false;
    let walking = false;
    let sawLoad = false;
    let scriptableOnce = false;
    let detach: (() => void) | null = null;
    let cancelClick: (() => void) | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const started = Date.now();
    let phaseNow: DeskPhase = "opening";

    const clearTimer = () => {
      if (timer != null) clearTimeout(timer);
      timer = null;
    };

    const setPhaseBoth = (next: DeskPhase) => {
      phaseNow = next;
      setPhase(next);
    };

    const yieldToUser = () => {
      if (stopped || yielded) return;
      if (phaseNow === "empty" || phaseNow === "live") return;
      yielded = true;
      walking = false;
      clearTimer();
      cancelClick?.();
      cancelClick = null;
      setPhaseBoth("yours");
    };
    yieldRef.current = yieldToUser;

    const arm = (doc: Document) => {
      detach?.();
      detach = bindYieldListeners(doc, yieldToUser);
    };

    const finishEmpty = () => {
      if (stopped || yielded || phaseNow === "yours") return;
      clearTimer();
      cancelClick?.();
      setPhaseBoth("empty");
    };

    let walkMisses = 0;

    const scheduleWalk = () => {
      clearTimer();
      timer = setTimeout(walk, WALK_DWELL_MS);
    };

    const retryWalk = () => {
      walkMisses += 1;
      if (walkMisses < 40) timer = setTimeout(walk, 300);
    };

    const walk = () => {
      if (stopped || yielded) return;
      const doc = frame.contentDocument;
      if (!doc || !dashboardReady(doc)) {
        retryWalk();
        return;
      }
      const link = nextWalkAnchor(doc);
      if (!link) {
        retryWalk();
        return;
      }
      walkMisses = 0;
      setPhaseBoth("walking");
      cancelClick?.();
      cancelClick = activateNavLink(link);
      scheduleWalk();
    };

    const tick = () => {
      if (stopped || yielded) return;
      const probe = probeEmbed(frame);
      if (probe.kind === "cross-origin") {
        if (scriptableOnce || walking) return;
        if (!sawLoad && Date.now() - started <= OPEN_BUDGET_MS) {
          timer = setTimeout(tick, 300);
          return;
        }
        clearTimer();
        setPhaseBoth("live");
        return;
      }
      if (probe.kind === "closed") {
        if (sawLoad || Date.now() - started > OPEN_BUDGET_MS) finishEmpty();
        else timer = setTimeout(tick, 300);
        return;
      }
      scriptableOnce = true;
      const doc = frame.contentDocument;
      if (!doc) return;
      arm(doc);
      if (dashboardReady(doc)) {
        if (!walking) {
          walking = true;
          setPhaseBoth("walking");
          scheduleWalk();
        }
        return;
      }
      if (embedLooksDown(doc) || Date.now() - started > OPEN_BUDGET_MS) {
        finishEmpty();
        return;
      }
      timer = setTimeout(tick, 300);
    };

    const onLoad = () => {
      if (stopped || yielded || phaseNow === "live") return;
      sawLoad = true;
      clearTimer();
      const probe = probeEmbed(frame);
      if (probe.kind === "scriptable" && frame.contentDocument) arm(frame.contentDocument);
      if (walking) {
        scheduleWalk();
        return;
      }
      tick();
    };

    frame.addEventListener("load", onLoad);
    tick();
    return () => {
      stopped = true;
      clearTimer();
      cancelClick?.();
      detach?.();
      frame.removeEventListener("load", onLoad);
      yieldRef.current = () => {};
    };
  }, []);

  const yieldFromShell = (event: { nativeEvent: Event }) => {
    if (shouldYieldToUser(event.nativeEvent)) yieldRef.current();
  };

  return (
    <div
      className="border border-hair bg-surface font-mono text-ink"
      onPointerDown={yieldFromShell}
      onWheel={yieldFromShell}
      onKeyDown={yieldFromShell}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hair px-2 py-1 text-[0.62rem] text-ink-mute">
        <span>digiquant · terminal</span>
        <span className="flex flex-wrap items-center gap-2">
          <span aria-live="polite">{deskStatus(phase)}</span>
          {phase === "opening" || phase === "walking" ? (
            <Button type="button" variant="outline" size="xs" onClick={() => yieldRef.current()}>
              {DESK_YIELD_LABEL}
            </Button>
          ) : null}
        </span>
      </div>
      {phase === "empty" ? (
        <p className="m-0 px-3 py-6 text-[0.75rem] leading-[1.5] text-ink-mute">{DESK_EMPTY_COPY}</p>
      ) : null}
      <iframe
        ref={frameRef}
        title="digiquant terminal"
        src={DESK_EMBED_SRC}
        loading="eager"
        hidden={phase === "empty"}
        className="block h-[min(46rem,calc(100svh-16rem))] min-h-[36rem] w-full border-0 bg-surface"
      />
    </div>
  );
}
