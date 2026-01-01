"use client";

import { useDeployUi } from "../stock/deploy-ui-context";
import {
  resolveWorkDisclosure,
  workVisibilityForView,
  type WorkDisclosure,
} from "../stock/skin-types";
import type { ChainRowMode } from "./chain-state";

export type DeployWorkDisclosure = {
  reasoningMode: ChainRowMode;
  toolCallsMode: ChainRowMode;
  disclosure: WorkDisclosure;
};

/**
 * The deploy's view level and row modes, resolved the way the digichat skin
 * resolves them before handing them to its thread (`skins/digichat.tsx`), for
 * skins that read them from context instead of props.
 */
export function useDeployWorkDisclosure(): DeployWorkDisclosure {
  const ui = useDeployUi();
  return {
    reasoningMode: ui.reasoning,
    toolCallsMode: ui.toolCalls,
    disclosure: resolveWorkDisclosure(workVisibilityForView(ui.view)),
  };
}

/** Base skins: a tool card shows its arguments while its call runs. */
export function useToolRowOpenWhileRunning(): boolean {
  const { toolCallsMode, disclosure } = useDeployWorkDisclosure();
  return toolCallsMode !== "off" && disclosure.openWhileRunning;
}
