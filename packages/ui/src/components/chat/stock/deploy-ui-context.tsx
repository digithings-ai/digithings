"use client";

/**
 * Deploy-driven UI knobs for the stock (baseline) Thread.
 * Provided by ProductStockShell — never imports Ink / CLI packages.
 */

import { createContext, useContext } from "react";
import type {
  ChainDisclosureMode,
  ThinkingMode,
  UserAlign,
  ViewMode,
} from "./skin-types";

export type DeployUiValue = {
  /** Effective reasoning disclosure (view mode + thinking override). */
  reasoning: ChainDisclosureMode;
  /** Effective tool-call disclosure (view mode only). */
  toolCalls: ChainDisclosureMode;
  /**
   * The raw view level, before it is folded into a disclosure mode. The
   * distinction matters: `quiet` is not "closed", it is "one summary line".
   */
  view: ViewMode;
  /** The raw thinking override, before folding. */
  thinking: ThinkingMode;
  userAlign: UserAlign;
};

export const DEFAULT_DEPLOY_UI: DeployUiValue = {
  reasoning: "collapsed",
  toolCalls: "collapsed",
  view: "balanced",
  thinking: "auto",
  userAlign: "right",
};

const DeployUiContext = createContext<DeployUiValue>(DEFAULT_DEPLOY_UI);

export const DeployUiProvider = DeployUiContext.Provider;

export function useDeployUi(): DeployUiValue {
  return useContext(DeployUiContext);
}

export function useDisclosureUi(kind: "reasoning" | "toolCalls") {
  const ui = useDeployUi();
  const mode = ui[kind];
  return {
    mode,
    visible: mode !== "off",
    defaultOpen: mode === "expanded",
    locked: false,
  };
}

/**
 * How the /view level folds the chain in skins that render it with plain
 * collapsibles (base, chatgpt). Collapsibles only read `defaultOpen` on mount,
 * so `key` changes with the level and a /view switch remounts them in the new
 * state. quiet: tool calls fold into the group's one summary line and thinking
 * stays folded even while it streams. balanced: today's layout (folded group
 * and cards; thinking opens while it streams). verbose: everything open.
 */
export type ViewDisclosure = {
  key: string;
  toolGroupOpen: boolean;
  toolCardOpen: boolean;
  reasoningOpen: (running: boolean) => boolean;
};

export function viewDisclosure(
  ui: Pick<DeployUiValue, "view" | "toolCalls" | "reasoning">,
): ViewDisclosure {
  const { view, toolCalls, reasoning } = ui;
  const verbose = toolCalls === "expanded";
  return {
    key: `${view}:${toolCalls}:${reasoning}`,
    toolGroupOpen: verbose,
    toolCardOpen: verbose,
    reasoningOpen: (running) =>
      reasoning === "expanded" || (running && view !== "quiet" && reasoning !== "collapsed"),
  };
}

export function useViewDisclosure(): ViewDisclosure {
  return viewDisclosure(useDeployUi());
}
