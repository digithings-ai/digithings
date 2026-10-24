/**
 * Model prices for cost gates. `limits.cost.prices` wins over this catalog.
 * The catalog file is the #6193 picker (`config/model-picker-catalog.json`).
 * This module only reads it. It does not call a provider, and a missing file
 * means no catalog prices.
 */

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Price } from "./store";

export function pricesFromCatalog(raw: unknown): Record<string, Price> {
  if (!raw || typeof raw !== "object") return {};
  const models = (raw as { models?: unknown }).models;
  if (!Array.isArray(models)) return {};
  const prices: Record<string, Price> = {};
  for (const row of models) {
    if (!row || typeof row !== "object") continue;
    const model = row as { id?: unknown; inputPerM?: unknown; outputPerM?: unknown };
    if (typeof model.id !== "string" || !model.id) continue;
    if (typeof model.inputPerM !== "number" || typeof model.outputPerM !== "number") continue;
    if (!Number.isFinite(model.inputPerM) || !Number.isFinite(model.outputPerM)) continue;
    prices[model.id] = { inputPerM: model.inputPerM, outputPerM: model.outputPerM };
  }
  return prices;
}

let loaded = false;
let cache: Record<string, Price> = {};

function catalogFile(): string | undefined {
  const candidates = [
    resolve(process.cwd(), "config/model-picker-catalog.json"),
    resolve(process.cwd(), "apps/digichat/config/model-picker-catalog.json"),
  ];
  return candidates.find((path) => existsSync(path));
}

export function loadCatalogPrices(): Record<string, Price> {
  if (loaded) return cache;
  loaded = true;
  const path = catalogFile();
  if (!path) return cache;
  try {
    cache = pricesFromCatalog(JSON.parse(readFileSync(path, "utf8")));
  } catch {
    cache = {};
  }
  return cache;
}

export function resetCatalogPricesForTests(): void {
  loaded = false;
  cache = {};
}
