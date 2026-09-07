"use client";

/**
 * Optional pre-send intercept for stock Composer (embed free-tier / BYOK hold).
 * When shouldHold returns true, ComposerPrimitive.Root onSubmit preventDefaults
 * so composer.send() never runs and POST /api/chat is not fired.
 */

import {
  createContext,
  useCallback,
  useContext,
  type FormEvent,
  type ReactNode,
} from "react";
import { useAui } from "@assistant-ui/react";

export type StockSendGateHandlers = {
  /**
   * Return true to swallow the submit (hold question / open settings).
   * Return false to let the default composer.send() proceed.
   */
  shouldHold: (text: string) => boolean;
  /** Called after shouldHold(true); text is already trimmed. */
  onHold: (text: string) => void;
  /** Called when submit is allowed through (e.g. arm turn charge). */
  onAllowSend?: () => void;
};

const StockSendGateContext = createContext<StockSendGateHandlers | null>(null);

export function StockSendGateProvider({
  handlers,
  children,
}: {
  handlers: StockSendGateHandlers | null;
  children: ReactNode;
}) {
  return (
    <StockSendGateContext.Provider value={handlers}>
      {children}
    </StockSendGateContext.Provider>
  );
}

export function useStockSendGate(): StockSendGateHandlers | null {
  return useContext(StockSendGateContext);
}

/**
 * Form onSubmit for ComposerPrimitive.Root. Must run before the primitive's
 * own handleSubmit (radix composeEventHandlers — preventDefault skips send).
 */
export function useStockComposerGateSubmit():
  | ((event: FormEvent<HTMLFormElement>) => void)
  | undefined {
  const gate = useStockSendGate();
  const aui = useAui();

  return useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      if (!gate) return;
      const text = aui.composer.getState().text.trim();
      if (!text) return;
      if (gate.shouldHold(text)) {
        event.preventDefault();
        aui.composer.setText("");
        gate.onHold(text);
        return;
      }
      gate.onAllowSend?.();
    },
    [aui, gate],
  );
}
