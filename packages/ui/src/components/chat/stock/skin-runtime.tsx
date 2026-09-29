"use client";

import { createContext, useContext, type ReactNode } from "react";

// Host-injected runtime for the catalog skins (WS4 Step 3).
//
// Skins render inside many hosts (product shell, /baseline catalog, embeds).
// Anything a skin needs that lives in the host app — error copy, session
// config, menu panes — enters through this context, never through an `@/`
// import (packages cannot import app code). Hosts provide values at their
// ThreadSkinView mount points; fields stay optional so a host that does not
// care keeps today's rendering.

// String-compatible mirror of the app's ParsedEmbedChatError. The app's
// parse/format fns assign directly to SkinErrorParsers.
export type ParsedSkinError = {
  code?: string;
  message?: string;
  detail?: string;
  raw: string;
};

export type SkinErrorParsers = {
  parseError: (error: Error | undefined) => ParsedSkinError | null;
  formatError: (error: Error | undefined) => string | null;
};

export type SkinRuntimeValue = {
  errorParsers?: SkinErrorParsers;
};

const SkinRuntimeContext = createContext<SkinRuntimeValue>({});

export const SkinRuntimeProvider = SkinRuntimeContext.Provider;

export function useSkinRuntime(): SkinRuntimeValue {
  return useContext(SkinRuntimeContext);
}

export function SkinRuntime({
  value,
  children,
}: {
  value: SkinRuntimeValue;
  children: ReactNode;
}) {
  return (
    <SkinRuntimeContext.Provider value={value}>
      {children}
    </SkinRuntimeContext.Provider>
  );
}
