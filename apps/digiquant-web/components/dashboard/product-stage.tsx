"use client";

import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type SyntheticEvent,
} from "react";
import { Button } from "@digithings/ui/ui";
import { DESK_GO_TYPE } from "@/components/desk/paths";
import { publicCatalogPages } from "@/components/desk/public-surface";
import {
  DESK_EMBED_SRC,
  OPEN_BUDGET_MS,
  bindYieldListeners,
  embedLooksDown,
  probeEmbed,
  shouldYieldToUser,
} from "./desk-walk";
import { TerminalScreen } from "./terminal-screen";
import {
  IDLE_RESUME_MS,
  REVEAL_REST,
  REVEAL_RETURN_MS,
  REVEAL_SWEEP_MS,
  TERMINAL_COPY,
  TERMINAL_TITLE,
  TOUR_DWELL_MS,
  WEB_COPY,
  WEB_EMPTY_COPY,
  WEB_TITLE,
  clampSplit,
  deskPathFromLocation,
  deskShellLoaded,
  nextTerminalPath,
  prevTerminalPath,
  revealShare,
  sentenceFits,
  splitFromPointer,
  type StagePhase,
} from "./surface-tour";

const PAGES = publicCatalogPages();
const HOME = PAGES[0]?.path ?? "/brief";
const KNOWN = new Set(PAGES.map((page) => page.path));

/** Terminal UI and the web app, both at the full preview size.
 *  A clip reveals a slice. The handle can sit on either edge.
 *  A pointer, wheel, or key inside a frame pauses the tour. */
export function ProductStage() {
  const stageRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);
  const pathRef = useRef(HOME);
  const holdRef = useRef<() => void>(() => {});
  const dragRef = useRef(false);
  const [path, setPath] = useState(HOME);
  const [share, setShare] = useState(REVEAL_REST);
  const [phase, setPhase] = useState<StagePhase>("opening");
  const phaseRef = useRef<StagePhase>("opening");
  const pageLabel = PAGES.find((page) => page.path === path)?.label ?? path;

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const started = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      if (dragRef.current) return;
      setShare(revealShare(now - started, false));
      if (now - started < REVEAL_SWEEP_MS + REVEAL_RETURN_MS) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  const showWeb = (next: string) => {
    const win = frameRef.current?.contentWindow;
    if (!win || !KNOWN.has(next)) return;
    win.postMessage({ type: DESK_GO_TYPE, path: next }, window.location.origin);
  };

  useEffect(() => {
    const frame = frameRef.current;
    let stopped = false;
    let held = false;
    let primed = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let idle: ReturnType<typeof setTimeout> | null = null;
    let probeTimer: ReturnType<typeof setTimeout> | null = null;
    let detach: (() => void) | null = null;
    let bound: Document | null = null;
    const started = Date.now();

    const clearTimer = () => {
      if (timer != null) clearTimeout(timer);
      timer = null;
    };
    const clearIdle = () => {
      if (idle != null) clearTimeout(idle);
      idle = null;
    };

    const publish = (next: StagePhase) => {
      if (phaseRef.current === next) return;
      phaseRef.current = next;
      setPhase(next);
    };

    const arm = (doc: Document) => {
      if (bound === doc) return;
      detach?.();
      bound = doc;
      try {
        detach = bindYieldListeners(doc, () => holdRef.current());
      } catch {
        detach = null;
      }
    };

    const webBlocked = (): StagePhase | null => {
      if (!frame) return "opening";
      const probe = probeEmbed(frame);
      if (probe.kind === "cross-origin") return "live";
      if (probe.kind === "closed") return Date.now() - started > OPEN_BUDGET_MS ? "empty" : "opening";
      const doc = frame.contentDocument;
      if (!doc) return "opening";
      arm(doc);
      if (deskShellLoaded(doc)) return null;
      if (embedLooksDown(doc)) return "empty";
      return Date.now() - started > OPEN_BUDGET_MS ? "empty" : "opening";
    };

    const syncFromWeb = () => {
      if (!held || !frame) return;
      const doc = frame.contentDocument;
      if (!doc) return;
      let pathname = "";
      try {
        pathname = doc.location.pathname;
      } catch {
        return;
      }
      const next = deskPathFromLocation(pathname);
      if (!KNOWN.has(next) || next === pathRef.current) return;
      pathRef.current = next;
      setPath(next);
    };

    const schedule = () => {
      clearTimer();
      timer = setTimeout(() => {
        advance();
        if (stopped || held) return;
        schedule();
      }, TOUR_DWELL_MS);
    };

    const prime = () => {
      if (primed || held || stopped) return;
      primed = true;
      schedule();
    };

    const publishSurface = () => {
      const blocked = webBlocked();
      if (blocked === "empty" || blocked === "live") {
        publish(blocked);
        prime();
        return;
      }
      if (held) {
        publish("yours");
        syncFromWeb();
        return;
      }
      if (blocked) {
        publish(blocked);
        return;
      }
      publish("touring");
      prime();
    };

    const advance = () => {
      if (stopped || held) return;
      const blocked = webBlocked();
      if (blocked === "opening") return;
      const next = nextTerminalPath(pathRef.current);
      pathRef.current = next;
      setPath(next);
      if (blocked === "empty" || blocked === "live") {
        publish(blocked);
        return;
      }
      const win = frame.contentWindow;
      if (win) win.postMessage({ type: DESK_GO_TYPE, path: next }, window.location.origin);
      publish("touring");
    };

    const resume = () => {
      if (stopped) return;
      held = false;
      publishSurface();
      if (primed) schedule();
    };

    const hold = () => {
      if (stopped) return;
      held = true;
      clearTimer();
      publishSurface();
      if (phaseRef.current !== "empty" && phaseRef.current !== "live") publish("yours");
      clearIdle();
      idle = setTimeout(resume, IDLE_RESUME_MS);
    };
    holdRef.current = hold;

    const probe = () => {
      if (stopped) return;
      publishSurface();
      probeTimer = setTimeout(probe, 300);
    };

    probe();
    return () => {
      stopped = true;
      clearTimer();
      clearIdle();
      if (probeTimer != null) clearTimeout(probeTimer);
      detach?.();
      holdRef.current = () => {};
    };
  }, []);

  const go = (next: string, user: boolean) => {
    if (next === pathRef.current || !KNOWN.has(next)) return;
    pathRef.current = next;
    setPath(next);
    showWeb(next);
    if (user) holdRef.current();
  };

  const onViewEvent = (event: SyntheticEvent) => {
    if (shouldYieldToUser(event.nativeEvent)) holdRef.current();
  };

  const onListKey = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    go(event.key === "ArrowDown" ? nextTerminalPath(pathRef.current) : prevTerminalPath(pathRef.current), true);
  };

  const takeHandle = () => {
    dragRef.current = true;
  };

  const resizeTo = (clientX: number) => {
    const stage = stageRef.current;
    if (!stage) return;
    const rect = stage.getBoundingClientRect();
    setShare(splitFromPointer(clientX, rect.left, rect.width));
  };

  const onHandleDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    takeHandle();
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeTo(event.clientX);
  };

  const onHandleMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
    resizeTo(event.clientX);
  };

  const onHandleKey = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight" && event.key !== "Home" && event.key !== "End") return;
    event.preventDefault();
    event.stopPropagation();
    takeHandle();
    if (event.key === "Home") {
      setShare(0);
      return;
    }
    if (event.key === "End") {
      setShare(1);
      return;
    }
    const step = event.key === "ArrowRight" ? 0.05 : -0.05;
    setShare((value) => clampSplit(value + step));
  };

  const handleLeft = `clamp(0px, calc(${share * 100}% - 0.5rem), calc(100% - 1rem))`;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex border border-hair" data-reveal={share === REVEAL_REST ? "rest" : "moving"}>
        <div className="min-w-0 overflow-hidden" style={{ width: `${share * 100}%` }} data-side="terminal">
          <SideCopy title={TERMINAL_TITLE} copy={TERMINAL_COPY} />
        </div>
        <div className="min-w-0 overflow-hidden border-s border-hair" style={{ width: `${(1 - share) * 100}%` }} data-side="web">
          <SideCopy title={WEB_TITLE} copy={WEB_COPY} />
        </div>
      </div>
      <div
        ref={stageRef}
        data-stage="desk"
        className="relative h-[min(40rem,calc(100svh-18rem))] min-h-[28rem] overflow-hidden border border-hair bg-surface"
        style={{ containerType: "inline-size" }}
      >
        <div
          className="absolute inset-0"
          data-pane="web"
          data-page={path}
          onPointerDown={onViewEvent}
          onWheel={onViewEvent}
          onKeyDown={onViewEvent}
        >
          {phase === "empty" ? (
            <p className="relative z-10 m-0 px-3 py-6 font-mono text-[0.75rem] leading-[1.5] text-ink-mute">{WEB_EMPTY_COPY}</p>
          ) : null}
          <iframe
            ref={frameRef}
            title="digiquant web app"
            src={DESK_EMBED_SRC}
            loading="eager"
            data-frame="full"
            className={`absolute inset-0 block h-full w-full border-0 bg-surface ${phase === "empty" ? "invisible" : ""}`}
          />
        </div>
        <div
          className="absolute inset-y-0 left-0 z-10 overflow-hidden"
          data-pane="terminal"
          data-page={path}
          style={{ width: `${share * 100}%` }}
          onPointerDown={onViewEvent}
          onWheel={onViewEvent}
          onKeyDown={onViewEvent}
        >
          <div className="absolute top-0 left-0 h-full" style={{ width: "100cqi" }} data-frame="full">
            <TerminalStage path={path} label={pageLabel} onListKey={onListKey} onNavigate={(next) => go(next, true)} />
          </div>
        </div>
        <Button
          type="button"
          variant="ghost"
          role="slider"
          aria-orientation="vertical"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(share * 100)}
          aria-label="Drag to reveal the terminal UI or the web app"
          className="absolute top-0 z-30 h-full w-4 rounded-none border-0 bg-transparent px-0 transition-none hover:bg-transparent active:translate-y-0"
          style={{ left: handleLeft }}
          onPointerDown={onHandleDown}
          onPointerMove={onHandleMove}
          onKeyDown={onHandleKey}
        >
          <span aria-hidden="true" className="block h-9 w-2.5 border border-hair bg-surface" />
        </Button>
      </div>
    </div>
  );
}

function SideCopy({ title, copy }: { title: string; copy: string }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLSpanElement>(null);
  const [fits, setFits] = useState(false);

  useLayoutEffect(() => {
    const box = boxRef.current;
    const text = textRef.current;
    if (!box || !text) return;
    const measure = () => {
      const styles = getComputedStyle(box);
      const pad = Number.parseFloat(styles.paddingLeft) + Number.parseFloat(styles.paddingRight);
      setFits(sentenceFits(text.scrollWidth, box.clientWidth - pad));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(box);
    return () => observer.disconnect();
  }, [copy]);

  return (
    <div ref={boxRef} className="relative px-3 py-2.5">
      <p className="m-0 font-mono text-[0.6875rem] tracking-[0.04em] text-ink">{title}</p>
      <span
        ref={textRef}
        aria-hidden="true"
        className="pointer-events-none absolute top-0 left-0 whitespace-nowrap text-[0.8125rem] leading-[1.55]"
        style={{ visibility: "hidden" }}
      >
        {copy}
      </span>
      {fits ? (
        <p data-fit="shown" className="m-0 mt-1 whitespace-nowrap text-[0.8125rem] leading-[1.55] text-ink-soft">
          {copy}
        </p>
      ) : null}
    </div>
  );
}

function TerminalStage({
  path,
  label,
  onListKey,
  onNavigate,
}: {
  path: string;
  label: string;
  onListKey: (event: ReactKeyboardEvent<HTMLElement>) => void;
  onNavigate: (path: string) => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col bg-surface font-mono text-ink">
      <header className="flex h-8 shrink-0 items-center justify-between gap-3 border-b border-hair px-2.5 font-mono text-[0.6875rem] tracking-[0.04em] text-ink-mute">
        <span className="truncate text-ink">
          digiquant · {label} · {path}
        </span>
        <span className="truncate">screens the terminal draws</span>
      </header>
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Terminal pages" className="w-[12rem] shrink-0 overflow-auto border-e border-hair" onKeyDown={onListKey}>
          {PAGES.map((item) => {
            const nested = item.path.split("/").filter(Boolean).length > 1;
            const current = item.path === path;
            return (
              <Button
                key={item.path}
                type="button"
                variant="ghost"
                size="xs"
                aria-current={current ? "page" : undefined}
                className={`h-7 w-full justify-start rounded-none px-2.5 font-mono text-[0.6875rem] font-normal tracking-[0.02em] ${nested ? "ps-5" : ""} ${current ? "bg-surface-2 text-ink" : "text-ink-mute"}`}
                onClick={() => onNavigate(item.path)}
              >
                {item.label}
              </Button>
            );
          })}
        </nav>
        <div key={path} className="desk-page-settle relative min-h-0 min-w-0 flex-1 overflow-hidden">
          <TerminalScreen path={path} />
        </div>
      </div>
    </div>
  );
}
