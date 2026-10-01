"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useMotionSafe } from "@digithings/ui";
import { MCP_COMMAND, MCP_COMMANDS, MCP_HELP_COMMAND, MCP_OPTIONS, type McpScope } from "@/app/_mcp";

const SCOPE_TONE: Record<McpScope, string> = {
  full: "text-ink",
  read: "text-ink-soft",
  roadmap: "text-ink-mute",
};

/** Lines print in as the block scrolls into view. Server render, reduced motion and a
 *  missing IntersectionObserver show every line from the start. */
function useArmed(safe: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!safe || !el || typeof IntersectionObserver === "undefined") {
      setArmed(false);
      return;
    }
    setArmed(true);
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          io.disconnect();
          setArmed(false);
        }
      },
      { threshold: 0.2 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [safe]);
  return { ref, armed };
}

function Line({ i, className, children }: { i: number; className?: string; children: ReactNode }) {
  return (
    <div
      className={`transition-opacity duration-300 group-data-[armed=true]:opacity-0 motion-reduce:transition-none ${className ?? ""}`}
      style={{ transitionDelay: `${i * 70}ms` }}
    >
      {children}
    </div>
  );
}

const PROMPT = (
  <span aria-hidden="true" className="text-accent">
    ${" "}
  </span>
);

/** The MCP band's terminal: the real server command, the tools it registers as a
 *  command list (select one for its detail) and its options. Text only; nothing here
 *  is a live connection. */
export function McpCli() {
  const safe = useMotionSafe();
  const { ref, armed } = useArmed(safe);
  const [open, setOpen] = useState<string>(MCP_COMMANDS[0]?.id ?? "");
  const optionsAt = MCP_COMMANDS.length + 3;

  return (
    <div
      ref={ref}
      data-armed={armed}
      className="group min-w-0 border border-hair bg-term-bg font-mono text-[0.78rem] leading-[1.7] text-ink-soft"
    >
      <div className="flex items-center justify-between gap-3 border-b border-hair px-4 py-2 text-[0.68rem] text-ink-mute">
        <span>digiquant · mcp</span>
        <span className="truncate">stdio · local · nothing here is a live connection</span>
      </div>
      <div className="flex flex-col gap-4 px-4 py-4">
        <div className="flex flex-col">
          <Line i={0} className="break-words text-ink">
            {PROMPT}
            {MCP_COMMAND}
          </Line>
          <Line i={1} className="text-ink-mute">
            # {MCP_COMMANDS.length} commands. pick one to read it
          </Line>
        </div>

        <div role="list" aria-label="MCP commands" className="flex flex-col">
          {MCP_COMMANDS.map((cmd, i) => {
            const selected = open === cmd.id;
            return (
              <Line key={cmd.id} i={i + 2}>
                <div role="listitem">
                  <button
                    type="button"
                    aria-expanded={selected}
                    aria-controls={`mcp-detail-${cmd.id}`}
                    onClick={() => setOpen(selected ? "" : cmd.id)}
                    className="grid w-full grid-cols-[1.25rem_minmax(0,1fr)_auto] items-baseline gap-x-2 bg-transparent p-0 text-start font-mono text-[length:inherit] leading-[inherit] text-ink-soft hover:bg-surface-2 focus-visible:bg-surface-2 sm:grid-cols-[1.25rem_8.5rem_minmax(0,1fr)_auto]"
                  >
                    <span aria-hidden="true" className={selected ? "text-accent" : "text-ink-mute"}>
                      {selected ? "▸" : ">"}
                    </span>
                    <span className="text-ink">{cmd.name}</span>
                    <span className="col-start-2 truncate text-ink-mute sm:col-start-auto">{cmd.tools}</span>
                    <span className={`col-start-3 row-start-1 sm:col-start-4 sm:row-start-auto ${SCOPE_TONE[cmd.scope]}`}>
                      [{cmd.scope}]
                    </span>
                  </button>
                  {selected ? (
                    <p
                      id={`mcp-detail-${cmd.id}`}
                      className="m-0 mb-1 ms-[1.25rem] border-s border-hair ps-3 font-sans text-[0.8125rem] leading-[1.55] text-ink-soft"
                    >
                      {cmd.detail}
                    </p>
                  ) : null}
                </div>
              </Line>
            );
          })}
        </div>

        <div className="flex flex-col">
          <Line i={optionsAt - 1} className="text-ink">
            {PROMPT}
            {MCP_HELP_COMMAND}
          </Line>
          {MCP_OPTIONS.map((opt, i) => (
            <Line key={opt.flag} i={optionsAt + i} className="grid grid-cols-[7.5rem_minmax(0,1fr)] gap-x-3">
              <span className="text-ink">{opt.flag}</span>
              <span className="text-ink-mute">{opt.text}</span>
            </Line>
          ))}
        </div>

        <div className="text-ink">
          {PROMPT}
          <span
            aria-hidden="true"
            className="inline-block h-[1em] w-[0.55ch] translate-y-[0.15em] animate-pulse bg-ink motion-reduce:animate-none"
          />
        </div>
      </div>
    </div>
  );
}
