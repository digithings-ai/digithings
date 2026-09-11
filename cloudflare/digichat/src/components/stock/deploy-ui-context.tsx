"use client";

/**
 * Deploy-driven UI knobs for the stock (baseline) Thread.
 * Provided by ProductStockShell — never imports Ink / CLI packages.
 */

import { createContext, useContext } from "react";
import type { DisclosureMode, UserAlign } from "@/lib/deploy-config/schema";
import {
  disclosureDefaultOpen,
  disclosureIsLocked,
  disclosureIsVisible,
} from "@/lib/deploy-config/schema";

export type DeployUiValue = {
  reasoning: DisclosureMode;
  toolCalls: DisclosureMode;
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
    visible: disclosureIsVisible(mode),
    defaultOpen: disclosureDefaultOpen(mode),
    locked: disclosureIsLocked(mode),
  };
}
