"use client";

import { createContext, useContext, type FC, type ReactNode } from "react";

/**
 * Whether the element renders inside the stock assistant-ui Thread.
 *
 * The stock Thread follows assistant-ui's default rounded shapes (base
 * registry, `@assistant-ui/react@^0.15.32`, and its shadcn base-nova
 * primitives). Several stock files are shared with other skins (markdown,
 * tool rows, reasoning, notices, the copy button and its tooltip), which keep
 * their square house dress. Those files read this flag and only switch to the
 * assistant-ui radius when it is set, so other skins render exactly as before.
 * React context crosses portals, so portaled tooltips and dialogs follow it.
 */
const StockShapeContext = createContext(false);

export const StockShapeProvider: FC<{ children: ReactNode }> = ({ children }) => (
  <StockShapeContext.Provider value={true}>{children}</StockShapeContext.Provider>
);

export function useStockShape(): boolean {
  return useContext(StockShapeContext);
}

/** The assistant-ui radius in the stock Thread, the square house radius elsewhere. */
export function stockRadius(stock: boolean, upstream: string, house = "rounded-none"): string {
  return stock ? upstream : house;
}
