/**
 * The trace grouping rules, as pure functions of the message parts and the
 * disclosure policy. The digichat skin's gallery thread and the base skins
 * both read them, so the two traces fold, open and count the same way and
 * differ only in how they look.
 *
 * Kept free of React so a test can call every rule with plain objects.
 */
import type { WorkDisclosure } from "../stock/skin-types";

/** The part fields the rules need. */
export type ChainPartLike = {
  readonly type: string;
  readonly text?: unknown;
};

/**
 * Disclosure behaviour for one kind of row inside the chain. `off` hides it,
 * `collapsed` renders it closed, `balanced` opens it while it streams,
 * `expanded` starts open and `locked_open` pins it open.
 */
export type ChainRowMode =
  | "off"
  | "collapsed"
  | "balanced"
  | "expanded"
  | "locked_open";

const isWork = (part: ChainPartLike | undefined) =>
  part?.type === "reasoning" || part?.type === "tool-call";

/** The message holds reasoning or a tool call somewhere. */
export function messageHasWork(parts: readonly (ChainPartLike | undefined)[]): boolean {
  return parts.some(isWork);
}

/**
 * Anything real arrived from the agent: reasoning, a tool call, the answer.
 * A status part (the connection state) is not content; it is the
 * pre-response phase, which is when the loading row belongs.
 */
export function messageHasContent(parts: readonly (ChainPartLike | undefined)[]): boolean {
  return parts.some((part) => part !== undefined && part.type !== "data");
}

/**
 * The chain holds real work. The grouping puts status and source parts into
 * the chain too; a chain of only those draws no header (the loading row
 * covers that phase).
 */
export function chainHoldsWork(
  parts: readonly (ChainPartLike | undefined)[],
  indices: readonly number[],
): boolean {
  return indices.some((index) => isWork(parts[index]));
}

/**
 * Only text ends a work run: a chain with non-empty text after it has
 * answered, so its work is over. A chain without one is still the agent's
 * current work, even if the model streams another run of tool calls.
 */
export function chainFollowedByText(
  parts: readonly (ChainPartLike | undefined)[],
  indices: readonly number[],
): boolean {
  const last = indices.length > 0 ? indices[indices.length - 1]! : -1;
  return parts.some((part, index) => {
    if (index <= last || part?.type !== "text") return false;
    return typeof part.text === "string" && part.text.trim() !== "";
  });
}

/** The tool calls in a tool group; sources and status parts do not count. */
export function chainToolCount(
  parts: readonly (ChainPartLike | undefined)[],
  indices: readonly number[],
): number {
  return indices.filter((index) => parts[index]?.type === "tool-call").length;
}

/** How long the chain waits before it folds away once its work is over. */
export const CHAIN_SETTLE_MS = 600;

/**
 * Whether the whole chain is open. The first manual toggle wins; otherwise
 * the verbose level keeps it open, the quiet level folds it as soon as the
 * answer starts, and the balanced level folds it once the work has settled.
 */
export function chainOpen({
  userOpen,
  openAtRest,
  foldOnAnswer,
  working,
  settled,
}: {
  userOpen: boolean | null;
  openAtRest: boolean;
  foldOnAnswer: boolean;
  working: boolean;
  settled: boolean;
}): boolean {
  return userOpen ?? (openAtRest ? true : foldOnAnswer ? working : !settled && working);
}

export type ChainGroupDisclosure = {
  /** Open on mount. */
  defaultOpen: boolean;
  /** Open while the group streams, folded again once it completes. */
  streamingOpen: boolean;
  /** Pinned open: the trigger does nothing. */
  locked: boolean;
};

/** The `N tool calls` group inside the chain. */
export function toolGroupDisclosure(
  disclosure: Pick<WorkDisclosure, "openAtRest" | "openWhileRunning">,
  mode: ChainRowMode,
  live: boolean,
): ChainGroupDisclosure {
  const locked = mode === "locked_open";
  return {
    locked,
    defaultOpen: disclosure.openAtRest || mode === "expanded" || locked,
    streamingOpen: (disclosure.openWhileRunning || mode === "balanced") && live,
  };
}

/** The reasoning box inside the chain. */
export function reasoningGroupDisclosure(
  disclosure: Pick<WorkDisclosure, "openAtRest" | "openWhileRunning">,
  mode: ChainRowMode,
  live: boolean,
): ChainGroupDisclosure {
  const locked = mode === "locked_open";
  return {
    locked,
    defaultOpen: disclosure.openAtRest || mode === "expanded" || locked,
    streamingOpen: live && (disclosure.openWhileRunning || mode === "balanced"),
  };
}
