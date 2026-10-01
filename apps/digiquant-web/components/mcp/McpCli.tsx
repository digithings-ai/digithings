"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useMotionSafe } from "@digithings/ui";
import { MCP_COMMAND, MCP_READ_COUNT, MCP_TOOLS } from "@/app/_mcp";
import {
  exampleArgs,
  groupByFamily,
  runDemo,
  type DemoLine,
  type McpScope,
  type McpTool,
} from "@/lib/mcp-demo";

const LINE_TONE: Record<DemoLine["kind"], string> = {
  call: "text-ink",
  ok: "text-ink-soft",
  err: "text-[var(--down)]",
  out: "text-ink-soft",
  mute: "text-ink-mute",
};
const LINE_MARK: Record<DemoLine["kind"], string> = { call: "→", ok: "✓", err: "✗", out: "←", mute: " " };

const PROMPT = (
  <span aria-hidden="true" className="text-accent">
    ${" "}
  </span>
);

function Pane({ className = "", children }: { className?: string; children: ReactNode }) {
  return <div className={`min-w-0 overflow-y-auto ${className}`}>{children}</div>;
}

function ToolList({
  tools,
  selected,
  onSelect,
}: {
  tools: McpTool[];
  selected: string;
  onSelect: (name: string) => void;
}) {
  const groups = useMemo(() => groupByFamily(tools), [tools]);
  const flat = tools.map((t) => t.name);
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const at = flat.indexOf(selected);
    const next = flat[Math.min(flat.length - 1, Math.max(0, at + (e.key === "ArrowDown" ? 1 : -1)))];
    if (!next) return;
    onSelect(next);
    e.currentTarget.querySelector<HTMLElement>(`[data-tool="${next}"]`)?.focus();
  };
  if (tools.length === 0) return <p className="m-0 px-1 text-ink-mute"># no tool matches</p>;
  return (
    <div role="listbox" aria-label="MCP tools" onKeyDown={onKey} className="flex flex-col">
      {groups.map((g) => (
        <div key={g.family} role="group" aria-label={g.family} className="flex flex-col">
          <p className="m-0 mt-2 text-ink-mute first:mt-0">
            # {g.family} ({g.tools.length})
          </p>
          {g.tools.map((t) => {
            const on = t.name === selected;
            return (
              <button
                key={t.name}
                type="button"
                role="option"
                aria-selected={on}
                data-tool={t.name}
                onClick={() => onSelect(t.name)}
                className={`grid w-full grid-cols-[1.1rem_minmax(0,1fr)_auto] items-baseline gap-x-1 p-0 text-start font-mono text-[length:inherit] leading-[inherit] hover:bg-surface-2 focus-visible:bg-surface-2 ${
                  on ? "bg-surface-2 text-ink" : "bg-transparent text-ink-soft"
                }`}
              >
                <span aria-hidden="true" className={on ? "text-accent" : "text-ink-mute"}>
                  {on ? "▸" : ">"}
                </span>
                <span className="truncate">{t.name}</span>
                <span className="text-ink-mute">[{t.scope === "read" ? "r" : "f"}]</span>
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function ToolDetail({ tool, serverScope }: { tool: McpTool; serverScope: McpScope }) {
  const safe = useMotionSafe();
  const [args, setArgs] = useState(() => JSON.stringify(exampleArgs(tool)));
  const [lines, setLines] = useState<DemoLine[]>([]);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach(clearTimeout);
  }, []);

  const run = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    const all = runDemo(tool, args, serverScope);
    if (!safe) {
      setLines(all);
      return;
    }
    setLines([]);
    all.forEach((line, i) => {
      timers.current.push(setTimeout(() => setLines((prev) => [...prev, line]), 160 * (i + 1)));
    });
  };

  return (
    <div className="flex flex-col gap-3">
      <div>
        <p className="m-0 text-ink">
          {PROMPT}mcp describe {tool.name}
        </p>
        <p className="m-0 mt-1 font-sans text-[0.8125rem] leading-[1.55] text-ink-soft">{tool.summary}</p>
        <p className="m-0 mt-1 text-ink-mute">
          [{tool.scope}] {tool.scope === "read" ? "served by --scope read and full" : "served by --scope full only"}
        </p>
      </div>

      <div>
        <p className="m-0 text-ink-mute"># args ({tool.params.length})</p>
        {tool.params.length === 0 ? (
          <p className="m-0 text-ink-soft">none</p>
        ) : (
          <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)_auto] gap-x-3">
            {tool.params.map((p) => (
              <div key={p.name} className="col-span-3 grid grid-cols-subgrid">
                <dt className="text-ink">{p.name}</dt>
                <dd className="m-0 truncate text-ink-mute">{p.type}</dd>
                <dd className="m-0 text-ink-mute">
                  {p.required ? "required" : `= ${JSON.stringify(p.default)}`}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </div>

      <div>
        <label htmlFor="mcp-args" className="m-0 block text-ink">
          {PROMPT}mcp call {tool.name}
        </label>
        <textarea
          id="mcp-args"
          value={args}
          onChange={(e) => setArgs(e.target.value)}
          spellCheck={false}
          rows={2}
          className="mt-1 block w-full resize-none border border-hair bg-transparent p-2 font-mono text-[0.72rem] leading-[1.5] text-ink focus-visible:border-ink-mute focus-visible:outline-none"
        />
        <div className="mt-2 flex items-center gap-3">
          <button
            type="button"
            onClick={run}
            className="border border-hair bg-transparent px-3 py-1 font-mono text-[0.72rem] text-ink hover:bg-surface-2 focus-visible:bg-surface-2"
          >
            run
          </button>
          <span className="text-ink-mute">demo · nothing is executed</span>
        </div>
      </div>

      <div aria-live="polite" className="min-h-[3rem]">
        {lines.map((line, i) => (
          <div key={i} className={`flex gap-2 ${LINE_TONE[line.kind]}`}>
            <span aria-hidden="true" className="shrink-0">
              {LINE_MARK[line.kind]}
            </span>
            {line.kind === "out" ? (
              <pre className="m-0 min-w-0 whitespace-pre-wrap break-words font-mono text-[length:inherit]">{line.text}</pre>
            ) : (
              <span className="min-w-0 break-words">{line.text}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/** The MCP band's terminal: the server command, then the full tool registry as a
 *  filterable command list. Select a tool for its arguments and run it in the demo, with
 *  the server scope switchable. Text only; nothing here is a live connection. */
export function McpCli() {
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState(MCP_TOOLS[0]?.name ?? "");
  const [scope, setScope] = useState<McpScope>("full");

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return MCP_TOOLS.filter((t) => (scope === "read" ? t.scope === "read" : true)).filter(
      (t) => !q || t.name.includes(q) || t.family.includes(q) || t.summary.toLowerCase().includes(q),
    );
  }, [filter, scope]);

  const tool = MCP_TOOLS.find((t) => t.name === selected) ?? MCP_TOOLS[0];
  const command = MCP_COMMAND.replace("--scope full", `--scope ${scope}`);

  return (
    <div className="min-w-0 border border-hair bg-term-bg font-mono text-[0.74rem] leading-[1.65] text-ink-soft">
      <div className="flex items-center justify-between gap-3 border-b border-hair px-4 py-2 text-[0.68rem] text-ink-mute">
        <span>digiquant · mcp</span>
        <span className="truncate">stdio · local · this page runs a demo, not a server</span>
      </div>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 px-4 pt-3">
        <p className="m-0 min-w-0 break-words text-ink">
          {PROMPT}
          {command}
        </p>
        <div role="group" aria-label="Server scope" className="flex items-center gap-2 text-ink-mute">
          <span># {visible.length} of {MCP_TOOLS.length} tools · scope</span>
          {(["full", "read"] as const).map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={scope === s}
              onClick={() => setScope(s)}
              className={`border px-2 py-0 font-mono text-[0.68rem] hover:bg-surface-2 ${
                scope === s ? "border-ink-mute bg-surface-2 text-ink" : "border-hair bg-transparent text-ink-mute"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>
      <p className="m-0 px-4 text-ink-mute">
        # {MCP_READ_COUNT} read-scope tools are what the dashboard chat gets; full adds backtest, optimize, export and fetches
      </p>
      <div className="grid gap-x-4 px-4 pb-4 pt-3 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="flex min-w-0 flex-col gap-2 border-hair md:border-e md:pe-4">
          <label className="flex items-baseline gap-2 text-ink">
            {PROMPT}
            <span className="shrink-0">tools | grep</span>
            <input
              type="search"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="name, family or text"
              aria-label="Filter tools"
              className="min-w-0 flex-1 border-0 border-b border-hair bg-transparent p-0 font-mono text-[length:inherit] text-ink placeholder:text-ink-mute focus-visible:border-ink-mute focus-visible:outline-none"
            />
          </label>
          <Pane className="h-[15rem] max-md:h-[10rem]">
            <ToolList tools={visible} selected={selected} onSelect={setSelected} />
          </Pane>
        </div>
        <Pane className="h-[19rem] max-md:mt-3 max-md:h-[16rem]">
          {tool ? <ToolDetail key={tool.name} tool={tool} serverScope={scope} /> : null}
        </Pane>
      </div>
    </div>
  );
}
