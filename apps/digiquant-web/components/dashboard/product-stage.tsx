"use client";

import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { Button } from "@digithings/ui/ui";
import { DESK_GO_TYPE } from "@/components/desk/paths";
import { publicCatalogPages } from "@/components/desk/public-surface";
import { DESK_EMBED_SRC } from "./desk-walk";
import { TerminalScreen } from "./terminal-screen";
import {
  SCROLL_SETTLE_MS,
  TERMINAL_COPY,
  TERMINAL_EDGE,
  TERMINAL_TITLE,
  WEB_COPY,
  WEB_EDGE,
  WEB_TITLE,
  armStageScroll,
  initialStageScroll,
  nextTerminalPath,
  onStageScroll,
  prevTerminalPath,
  type StageScroll,
  type Surface,
} from "./surface-tour";

const PAGES = publicCatalogPages();
const HOME = PAGES[0]?.path ?? "/brief";
const KNOWN = new Set(PAGES.map((page) => page.path));

/** One centered desk. It opens on the terminal UI. The first scroll after the
 *  stage has settled on screen slides it to the web app and leaves it there.
 *  The toggle switches either way. */
export function ProductStage() {
  const stageRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);
  const pathRef = useRef(HOME);
  const scrollRef = useRef<StageScroll>(initialStageScroll());
  const [path, setPath] = useState(HOME);
  const [surface, setSurface] = useState<Surface>("terminal");
  const pageLabel = PAGES.find((page) => page.path === path)?.label ?? path;

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    let visible = false;
    let settle: ReturnType<typeof setTimeout> | null = null;
    const observer = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting && entry.intersectionRatio >= 0.55;
        if (!visible && settle != null) {
          clearTimeout(settle);
          settle = null;
        }
      },
      { threshold: [0, 0.55] },
    );
    observer.observe(stage);

    const publish = (next: StageScroll) => {
      scrollRef.current = next;
      setSurface(next.surface);
    };

    const onScroll = () => {
      const next = onStageScroll(scrollRef.current, visible);
      if (next !== scrollRef.current) publish(next);
      if (next.slid || !visible) return;
      if (settle != null) clearTimeout(settle);
      settle = setTimeout(() => {
        settle = null;
        const armed = armStageScroll(scrollRef.current, visible);
        if (armed !== scrollRef.current) scrollRef.current = armed;
      }, SCROLL_SETTLE_MS);
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", onScroll);
      if (settle != null) clearTimeout(settle);
    };
  }, []);

  const showWeb = (next: string) => {
    const win = frameRef.current?.contentWindow;
    if (!win || !KNOWN.has(next)) return;
    win.postMessage({ type: DESK_GO_TYPE, path: next }, window.location.origin);
  };

  const go = (next: string) => {
    if (next === pathRef.current || !KNOWN.has(next)) return;
    pathRef.current = next;
    setPath(next);
    showWeb(next);
  };

  const choose = (next: Surface) => {
    scrollRef.current = { ...scrollRef.current, surface: next };
    setSurface(next);
  };

  const onListKey = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    go(event.key === "ArrowDown" ? nextTerminalPath(pathRef.current) : prevTerminalPath(pathRef.current));
  };

  const copy = surface === "terminal" ? TERMINAL_COPY : WEB_COPY;
  const edge = surface === "terminal" ? TERMINAL_EDGE : WEB_EDGE;
  const title = surface === "terminal" ? TERMINAL_TITLE : WEB_TITLE;

  return (
    <div className="mx-auto flex w-full max-w-[72rem] flex-col gap-3">
      <div role="group" aria-label="Show the terminal UI or the web app" className="flex w-fit border border-hair">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-pressed={surface === "terminal"}
          className={`rounded-none font-mono text-[0.72rem] font-normal ${surface === "terminal" ? "bg-surface-2 text-ink" : "text-ink-mute"}`}
          onClick={() => choose("terminal")}
        >
          {TERMINAL_TITLE}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-pressed={surface === "web"}
          className={`rounded-none border-s border-hair font-mono text-[0.72rem] font-normal ${surface === "web" ? "bg-surface-2 text-ink" : "text-ink-mute"}`}
          onClick={() => choose("web")}
        >
          {WEB_TITLE}
        </Button>
      </div>
      <div data-surface-copy={surface} className="border border-hair px-4 py-3">
        <p className="m-0 font-mono text-[0.72rem] tracking-[0.04em] text-ink">{title}</p>
        <p className="m-0 mt-2 max-w-[68ch] text-[0.9375rem] leading-[1.6] text-ink-soft">{copy}</p>
        <p className="m-0 mt-2 max-w-[68ch] text-[0.9375rem] leading-[1.6] text-ink">{edge}</p>
      </div>
      <div
        ref={stageRef}
        data-stage="desk"
        data-surface={surface}
        className="relative h-[min(40rem,calc(100svh-18rem))] min-h-[28rem] overflow-hidden border border-hair bg-surface"
      >
        <div
          className="flex h-full w-[200%] motion-reduce:transition-none motion-safe:transition-transform motion-safe:duration-700 motion-safe:ease-out"
          style={{ transform: surface === "web" ? "translateX(-50%)" : "translateX(0)" }}
        >
          <div className="h-full w-1/2" data-pane="terminal" data-page={path}>
            <TerminalStage path={path} label={pageLabel} onListKey={onListKey} onNavigate={go} />
          </div>
          <div className="h-full w-1/2" data-pane="web" data-page={path}>
            <iframe
              ref={frameRef}
              title="digiquant web app"
              src={DESK_EMBED_SRC}
              loading="eager"
              data-frame="full"
              className="block h-full w-full border-0 bg-surface"
            />
          </div>
        </div>
      </div>
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
