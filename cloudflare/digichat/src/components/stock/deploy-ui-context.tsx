"use client";

/**
 * Deploy-driven UI knobs for the stock (baseline) Thread.
 * Provided by ProductStockShell — never imports Ink / CLI packages.
 */

import { createContext, useContext } from "react";
import type { UserAlign } from "@/lib/deploy-config/schema";
import type { ChainDisclosureMode } from "@/lib/view-modes";

export type DeployUiValue = {
  /** Effective reasoning disclosure (view mode + thinking override). */
  reasoning: ChainDisclosureMode;
  /** Effective tool-call disclosure (view mode only). */
  toolCalls: ChainDisclosureMode;
  userAlign: UserAlign;
};

export const DEFAULT_DEPLOY_UI: DeployUiValue = {
  reasoning: "collapsed",
  toolCalls: "collapsed",
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
