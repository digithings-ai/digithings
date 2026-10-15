"use client";

import { useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import { Button } from "@digithings/ui/ui";
import { MCP_COMMAND, MCP_TOOLS } from "@/app/_mcp";
import { fetchGatewayCall } from "@/lib/gateway/gateway-client";
import { cycleName, exampleArgs, groupByFamily, validateArgs, type McpTool } from "@/lib/mcp-demo";

type TryResult = { status: number; ms: number; source: "gateway"; body: string };

const PROMPT = (
  <span aria-hidden="true" className="text-accent">
    ${" "}
  </span>
);

/** Pane scroller only: thin ink-mute thumb, no track paint. Not the page scrollbar. */
const PANE_SCROLL =
  "[scrollbar-width:thin] [scrollbar-color:color-mix(in_srgb,var(--ink-mute)_50%,transparent)_transparent] [&::-webkit-scrollbar]:h-1.5 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar]:bg-transparent [&::-webkit-scrollbar-track]:border-0 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:border-0 [&::-webkit-scrollbar-thumb]:bg-[color-mix(in_srgb,var(--ink-mute)_50%,transparent)] [&::-webkit-scrollbar-corner]:bg-transparent";

function Pane({ className = "", children }: { className?: string; children: ReactNode }) {
  return <div className={`min-w-0 overflow-y-auto ${PANE_SCROLL} ${className}`}>{children}</div>;
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
    e.stopPropagation();
    const next = cycleName(flat, selected, e.key === "ArrowDown" ? 1 : -1);
    onSelect(next);
    e.currentTarget.querySelector<HTMLElement>(`[data-tool="${CSS.escape(next)}"]`)?.focus();
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
                <span className="text-ink-mute">{t.family}</span>
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function ToolDetail({ tool }: { tool: McpTool }) {
  const [args, setArgs] = useState(() => JSON.stringify(exampleArgs(tool), null, 2));
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<TryResult | null>(null);

  const execute = async () => {
    const started = performance.now();
    let parsed: unknown;
    try {
      parsed = args.trim() ? JSON.parse(args) : {};
    } catch {
      setResult({ status: 400, ms: 0, source: "gateway", body: "arguments are not valid JSON" });
      return;
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      setResult({ status: 400, ms: 0, source: "gateway", body: "arguments must be a JSON object" });
      return;
    }
    const errors = validateArgs(tool, parsed as Record<string, unknown>);
    if (errors.length > 0) {
      setResult({ status: 400, ms: 0, source: "gateway", body: errors.join("\n") });
      return;
    }
    setBusy(true);
    const live = await fetchGatewayCall(tool.name, parsed as Record<string, unknown>);
    setBusy(false);
    if (!live.ok) {
      const reason =
        live.error === "unset"
          ? "The local gateway URL is not set. Start the gateway and set NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL to its loopback address."
          : live.error === "unsafe"
            ? "The gateway URL is not a loopback address."
            : live.error === "nonlocal-page"
              ? "This page is not served from localhost, so the gateway stays closed."
              : live.error;
      setResult({
        status: 0,
        ms: Math.round(performance.now() - started),
        source: "gateway",
        body: reason,
      });
      return;
    }
    setResult({
      status: live.status,
      ms: live.envelope.latencyMs || Math.round(performance.now() - started),
      source: "gateway",
      body: JSON.stringify(live.envelope, null, 2),
    });
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-hair pb-2">
        <p className="m-0 text-ink">
          <span className="text-accent">POST</span> /tools/{tool.name}
        </p>
        <p className="m-0 text-ink-mute">live · local gateway</p>
      </div>
      <p className="m-0 font-sans text-[0.8125rem] leading-[1.55] text-ink-soft">{tool.summary}</p>

      <div className="min-h-0">
        <p className="m-0 text-ink-mute">parameters</p>
        {tool.params.length === 0 ? (
          <p className="m-0 text-ink-soft">none</p>
        ) : (
          <table className="mt-1 w-full border-collapse text-start">
            <thead>
              <tr className="text-ink-mute">
                <th className="py-0.5 pe-3 text-start font-normal">name</th>
                <th className="py-0.5 pe-3 text-start font-normal">type</th>
                <th className="py-0.5 text-start font-normal">required</th>
              </tr>
            </thead>
            <tbody>
              {tool.params.map((p) => (
                <tr key={p.name} className="border-t border-hair">
                  <td className="py-0.5 pe-3 text-ink">{p.name}</td>
                  <td className="py-0.5 pe-3 text-ink-mute">{p.type}</td>
                  <td className="py-0.5 text-ink-mute">{p.required ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="flex shrink-0 flex-col">
        <label htmlFor="mcp-args" className="m-0 block text-ink-mute">
          request body
        </label>
        <textarea
          id="mcp-args"
          value={args}
          onChange={(e) => setArgs(e.target.value)}
          spellCheck={false}
          rows={4}
          className="mt-1 block min-h-[5.5rem] w-full resize-y border border-hair bg-transparent p-2 font-mono text-[0.72rem] leading-[1.5] text-ink focus-visible:border-ink-mute focus-visible:outline-none"
        />
        <div className="mt-2 flex shrink-0 items-center gap-3">
          <Button
            type="button"
            variant="outline"
            size="xs"
            onClick={() => void execute()}
            disabled={busy}
            className="font-mono text-[0.72rem] font-normal"
          >
            {busy ? "sending" : "Execute"}
          </Button>
          <span className="text-ink-mute">POST /v1/tools/call</span>
        </div>
      </div>

      <div aria-live="polite" className="shrink-0 border border-hair p-2">
        {result ? (
          <>
            <p className={`m-0 ${result.status >= 400 || result.status === 0 ? "text-[var(--down)]" : "text-ink"}`}>
              {result.status || "—"} · {result.ms} ms · {result.source}
            </p>
            <pre className="m-0 mt-1 max-h-[12rem] overflow-auto whitespace-pre-wrap break-words font-mono text-[0.72rem] text-ink-soft">
              {result.body}
            </pre>
          </>
        ) : (
          <p className="m-0 text-ink-mute">response</p>
        )}
      </div>
    </div>
  );
}

/** The MCP band's terminal: one list of every audited tool. Execute posts to the
 *  local gateway, which calls that tool on the digiquant MCP server. */
export function McpCli() {
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState(MCP_TOOLS[0]?.name ?? "");

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return MCP_TOOLS.filter(
      (t) => !q || t.name.includes(q) || t.family.includes(q) || t.summary.toLowerCase().includes(q),
    );
  }, [filter]);

  const tool = MCP_TOOLS.find((t) => t.name === selected) ?? MCP_TOOLS[0];
  const command = MCP_COMMAND;

  const onShellKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const tag = (e.target as HTMLElement).tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    e.preventDefault();
    const next = cycleName(
      visible.map((t) => t.name),
      selected,
      e.key === "ArrowDown" ? 1 : -1,
    );
    setSelected(next);
    e.currentTarget.querySelector<HTMLElement>(`[data-tool="${CSS.escape(next)}"]`)?.scrollIntoView({ block: "nearest" });
  };

  return (
    <div
      tabIndex={0}
      onKeyDown={onShellKey}
      className="flex h-[calc(100svh-var(--nav-shell-h,62px))] max-h-[52rem] min-h-[32rem] min-w-0 flex-1 flex-col overflow-hidden border border-hair bg-term-bg font-mono text-[0.74rem] leading-[1.65] text-ink-soft outline-none focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-[-1px] focus-visible:outline-hair"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 px-4 pt-3">
        <p className="m-0 min-w-0 break-words text-ink">
          {PROMPT}
          {command}
        </p>
        <p className="m-0 text-ink-mute">
          # {visible.length} of {MCP_TOOLS.length} tools
        </p>
      </div>
      <p className="m-0 px-4 text-ink-mute"># one list. Execute runs the tool on the local gateway.</p>
      <div className="grid min-h-0 flex-1 gap-x-4 px-4 pb-4 pt-3 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="flex min-h-0 min-w-0 flex-col gap-2 border-hair md:border-e md:pe-4">
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
          <Pane className="min-h-[16rem] flex-1 max-md:min-h-[12rem]">
            <ToolList tools={visible} selected={selected} onSelect={setSelected} />
          </Pane>
        </div>
        <Pane className="min-h-[20rem] flex-1 max-md:mt-3">
          {tool ? <ToolDetail key={tool.name} tool={tool} /> : null}
        </Pane>
      </div>
    </div>
  );
}
