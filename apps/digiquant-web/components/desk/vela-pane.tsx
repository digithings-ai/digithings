"use client";

import { useEffect, useRef, useState } from "react";
import type { VelaWorkspace } from "@luxalgo/vela/workspace";
import { VELA_UNAVAILABLE, velaWorkspaceOptions } from "./vela-options";

/** LuxAlgo Vela workspace. One chart. Binance and Coinbase. A failed mount keeps this chrome. */
export function VelaPane() {
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const host = ref.current;
    if (!host) return;
    let dead = false;
    let workspace: VelaWorkspace | null = null;

    const fail = () => {
      if (!dead) setFailed(true);
    };

    const mount = async () => {
      const [{ VelaWorkspace: Workspace }, { BinanceProvider }, { CoinbaseProvider }] = await Promise.all([
        import("@luxalgo/vela/workspace"),
        import("@luxalgo/vela/providers/binance"),
        import("@luxalgo/vela/providers/coinbase"),
      ]);
      if (dead) return;
      workspace = new Workspace(host, velaWorkspaceOptions(BinanceProvider, CoinbaseProvider));
    };

    void mount().catch(fail);
    return () => {
      dead = true;
      workspace?.destroy();
    };
  }, []);

  return (
    <div className="flex h-full min-h-0 w-full flex-1 flex-col bg-black">
      <div className="relative min-h-0 flex-1">
        <div ref={ref} className="absolute inset-0" />
      </div>
      {failed ? (
        <p aria-live="polite" className="m-0 flex h-7 shrink-0 items-center border-t border-hair px-2.5 font-mono text-[0.6875rem] tracking-[0.04em] text-ink-mute">
          {VELA_UNAVAILABLE}
        </p>
      ) : null}
    </div>
  );
}
