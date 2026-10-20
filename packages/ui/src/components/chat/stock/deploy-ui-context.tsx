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
