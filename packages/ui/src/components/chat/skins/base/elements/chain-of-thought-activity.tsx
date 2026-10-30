"use client";

import {
  Children,
  Fragment,
  isValidElement,
  useCallback,
  useRef,
  useState,
  type FC,
  type ReactElement,
  type ReactNode,
} from "react";
import {
  useAuiState,
  useScrollLock,
  type MessagePrimitive,
} from "@assistant-ui/react";
import { toolRowTitle } from "../../../stock/tool-display";
import { EN_TRACE_T, useTraceT, type TraceT } from "../../../trace-i18n";
import {
  RunActivity,
  type RunActivityEntry,
  type RunActivityStatus,
} from "../aui-default/run-activity";

/**
 * One `group-chainOfThought` node from `MessagePrimitive.GroupedParts`, shown
 * as assistant-ui's Run activity element: a single summary line ("Thought and
 * used 2 tools") that expands to the reasoning and tool calls in their
 * original order. The answer text stays outside, as upstream intends.
 *
 * GroupedParts coalesces the chain's adjacent reasoning parts into
 * `group-reasoning` and its adjacent tool calls into `group-tool`; each of
 * those becomes one Run activity entry.
 */

type ChainPart = { readonly type: string; readonly toolName?: string };

export type ChainRun =
  | { readonly kind: "reasoning"; readonly indices: readonly number[] }
  | {
      readonly kind: "tool";
      readonly indices: readonly number[];
      readonly toolNames: readonly string[];
    };

/** Split the chain's part indices into the runs GroupedParts renders. */
export function chainRuns(
  parts: readonly (ChainPart | undefined)[],
  indices: readonly number[],
): ChainRun[] {
  const runs: ChainRun[] = [];
  for (const index of indices) {
    const part = parts[index];
    if (!part) continue;
    const kind = part.type === "reasoning" ? "reasoning" : "tool";
    const last = runs[runs.length - 1];
    if (last && last.kind === kind) {
      runs[runs.length - 1] =
        last.kind === "tool"
          ? {
              kind: "tool",
              indices: [...last.indices, index],
              toolNames: [...last.toolNames, toolRowTitle(part.toolName ?? "")],
            }
          : { kind: "reasoning", indices: [...last.indices, index] };
    } else {
      runs.push(
        kind === "tool"
          ? {
              kind: "tool",
              indices: [index],
              toolNames: [toolRowTitle(part.toolName ?? "")],
            }
          : { kind: "reasoning", indices: [index] },
      );
    }
  }
  return runs;
}

type MessageStatusLike =
  | { readonly type: string; readonly reason?: string }
  | undefined;

export function chainStatus(
  groupRunning: boolean,
  messageStatus: MessageStatusLike,
): RunActivityStatus {
  if (groupRunning) return "running";
  if (messageStatus?.type === "requires-action") return "requires-action";
  if (messageStatus?.type === "incomplete") {
    if (messageStatus.reason === "cancelled") return "cancelled";
    if (messageStatus.reason === "error") return "error";
    // A chain that finished before the turn stopped still completed.
  }
  return "complete";
}

/** What the chain did, as the folded summary reads once it settles. */
export function chainSummary(runs: readonly ChainRun[], tr: TraceT = EN_TRACE_T): string {
  const thought = runs.some((run) => run.kind === "reasoning");
  const tools = runs.reduce(
    (count, run) => count + (run.kind === "tool" ? run.indices.length : 0),
    0,
  );
  if (thought && tools > 0) return tr.plural("thoughtAndUsedTools", tools);
  if (tools > 0) return tr.plural("usedTools", tools);
  return tr.t("thought");
}

export function chainStatusLabel(
  status: RunActivityStatus,
  runs: readonly ChainRun[],
  tr: TraceT = EN_TRACE_T,
): string {
  switch (status) {
    case "running":
      return runs[runs.length - 1]?.kind === "tool" ? tr.t("working") : tr.t("thinking");
    case "requires-action":
      return tr.t("needsInput");
    case "cancelled":
      return `${tr.t("stopped")} · ${chainSummary(runs, tr)}`;
    case "error":
      return `${tr.t("failed")} · ${chainSummary(runs, tr)}`;
    default:
      return chainSummary(runs, tr);
  }
}

function entryLabel(run: ChainRun, tr: TraceT): string {
  if (run.kind === "reasoning") return tr.t("thinking");
  return run.toolNames[run.toolNames.length - 1] ?? tr.t("toolFallbackName");
}

/**
 * GroupedParts hands a group its rendered sub-groups wrapped in a fragment.
 * Unwrap it so each sub-group lands in its own entry; anything unexpected
 * falls back to a single entry holding everything.
 */
function childNodes(children: ReactNode): ReactNode[] {
  const top = Children.toArray(children);
  if (top.length === 1) {
    const only = top[0];
    if (isValidElement(only) && only.type === Fragment) {
      return Children.toArray(
        (only as ReactElement<{ children?: ReactNode }>).props.children,
      );
    }
  }
  return top;
}

export const ChainOfThoughtActivity: FC<{
  group: MessagePrimitive.GroupedParts.GroupPart;
  /** Open on mount (the verbose /view level). */
  defaultOpen?: boolean;
  children: ReactNode;
}> = ({ group, defaultOpen = false, children }) => {
  const parts = useAuiState((s) => s.message.parts) as readonly (
    | ChainPart
    | undefined
  )[];
  const messageStatus = useAuiState(
    (s) => s.message.status,
  ) as MessageStatusLike;
  const tr = useTraceT();
  const [open, setOpen] = useState(defaultOpen);
  const rootRef = useRef<HTMLDivElement | null>(null);
  // Upstream: lock the thread viewport's scroll before changing `open`.
  const lockScroll = useScrollLock(rootRef, 200);
  const onOpenChange = useCallback(
    (next: boolean) => {
      lockScroll();
      setOpen(next);
    },
    [lockScroll],
  );

  const runs = chainRuns(parts, group.indices);
  const status = chainStatus(group.status.type === "running", messageStatus);
  const nodes = childNodes(children);

  const entries: RunActivityEntry[] =
    nodes.length === runs.length
      ? runs.map((run, i) => ({
          id: `${run.kind}-${run.indices[0]}`,
          kind: run.kind === "reasoning" ? "commentary" : "tool",
          label: entryLabel(run, tr),
          content: nodes[i],
        }))
      : [
          {
            id: `chain-${group.indices[0] ?? 0}`,
            kind: "tool",
            label: runs.length ? entryLabel(runs[runs.length - 1]!, tr) : "",
            content: children,
          },
        ];

  return (
    <div ref={rootRef} data-slot="aui_chain-of-thought" className="my-1">
      <RunActivity
        status={status}
        statusLabel={chainStatusLabel(status, runs, tr)}
        entries={entries}
        open={open}
        onOpenChange={onOpenChange}
      />
    </div>
  );
};
