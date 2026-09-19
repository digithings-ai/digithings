"use client";

import {
  ActivityIcon,
  AlertTriangleIcon,
  CheckCircle2Icon,
  DatabaseZapIcon,
  GaugeIcon,
  ServerCogIcon,
} from "lucide-react";
import type { CSSProperties } from "react";
import { useSkinChrome } from "@/components/stock/skin-chrome";

export function ProductDashboard() {
  const chrome = useSkinChrome();
  const productName = chrome.title?.trim() || "Northstar Sync";
  const themeStyle = {
    "--support-accent": chrome.accent?.color ?? "#2563eb",
    "--support-border": "#d8dee8",
    "--support-muted": "#64748b",
    "--support-success": "#15803d",
    "--support-warning": "#b45309",
  } as CSSProperties;

  return (
    <main className="h-full overflow-auto bg-slate-100 text-slate-950" style={themeStyle}>
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="grid size-9 place-items-center rounded-md bg-[var(--support-accent)] text-white">
              <DatabaseZapIcon className="size-5" />
            </div>
            <div>
              <div className="font-semibold leading-tight">{productName}</div>
              <div className="text-xs text-slate-500">{"Northstar Cloud"}</div>
            </div>
          </div>
          <div className="hidden items-center gap-2 rounded-md border border-[var(--support-border)] bg-white px-3 py-1.5 text-xs text-[var(--support-warning)] sm:flex">
            <AlertTriangleIcon className="size-4" />
            {"Workflow attention needed in us-west"}
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl gap-5 px-4 py-5 sm:px-6 lg:grid-cols-[240px_1fr]">
        <aside className="hidden rounded-lg border border-slate-200 bg-white p-4 lg:block">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
            {"Workspace"}
          </div>
          <div className="mt-2 font-semibold">{"Acme Operations"}</div>
          <div className="mt-1 text-sm text-slate-500">{"Scale plan, us-west"}</div>
          <nav className="mt-6 grid gap-1 text-sm">
            <div className="rounded-md px-3 py-2 text-slate-600 first:bg-slate-100 first:text-slate-950">{"Overview"}</div>
<div className="rounded-md px-3 py-2 text-slate-600 first:bg-slate-100 first:text-slate-950">{"Connectors"}</div>
<div className="rounded-md px-3 py-2 text-slate-600 first:bg-slate-100 first:text-slate-950">{"Records"}</div>
<div className="rounded-md px-3 py-2 text-slate-600 first:bg-slate-100 first:text-slate-950">{"Assistant"}</div>
          </nav>
        </aside>
        <section className="grid gap-5">
          <div className="rounded-lg border border-slate-200 bg-white p-5">
    <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
      <div>
        <h1 className="text-xl font-semibold">{"Workspace overview"}</h1>
        <p className="mt-1 text-sm text-[var(--support-muted)]">{"Live connector health with an embedded integration support assistant."}</p>
      </div>
      <div className="inline-flex w-fit items-center gap-2 rounded-md bg-emerald-50 px-3 py-2 text-sm text-[var(--support-success)]">
        <CheckCircle2Icon className="size-4" />
        {"Sync degraded"}
      </div>
    </div>
    <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
    <div className="text-sm text-slate-500">{"Sync success"}</div>
    <div className="mt-2 text-2xl font-semibold">{"98.4%"}</div>
    <div className="mt-1 text-xs text-slate-500">{"-1.8%"}</div>
  </div>
<div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
    <div className="text-sm text-slate-500">{"Retry queue"}</div>
    <div className="mt-2 text-2xl font-semibold">{"12"}</div>
    <div className="mt-1 text-xs text-slate-500">{"+3"}</div>
  </div>
<div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
    <div className="text-sm text-slate-500">{"Avg response"}</div>
    <div className="mt-2 text-2xl font-semibold">{"1h 42m"}</div>
    <div className="mt-1 text-xs text-slate-500">{"-18m"}</div>
  </div>
<div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
    <div className="text-sm text-slate-500">{"Services healthy"}</div>
    <div className="mt-2 text-2xl font-semibold">{"4 / 5"}</div>
    <div className="mt-1 text-xs text-slate-500">{"Sync degraded"}</div>
  </div>
  </div>
  </div>
<div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
    <div className="rounded-lg border border-slate-200 bg-white p-5">
    <div className="flex items-center gap-2">
      <ServerCogIcon className="size-5 text-[var(--support-accent)]" />
      <h2 className="font-semibold">{"Connector areas"}</h2>
    </div>
    <div className="mt-4 grid gap-3">
      <div className="flex items-center justify-between gap-3 rounded-md border border-slate-200 p-3">
        <div>
          <div className="font-medium">{"Sync Engine"}</div>
          <div className="text-sm text-slate-500">{"Retry latency high"}</div>
        </div>
        <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
          {"Degraded"}
        </span>
      </div>
<div className="flex items-center justify-between gap-3 rounded-md border border-slate-200 p-3">
        <div>
          <div className="font-medium">{"API"}</div>
          <div className="text-sm text-slate-500">{"Normal latency"}</div>
        </div>
        <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
          {"Operational"}
        </span>
      </div>
<div className="flex items-center justify-between gap-3 rounded-md border border-slate-200 p-3">
        <div>
          <div className="font-medium">{"Dashboard"}</div>
          <div className="text-sm text-slate-500">{"No errors"}</div>
        </div>
        <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
          {"Operational"}
        </span>
      </div>
<div className="flex items-center justify-between gap-3 rounded-md border border-slate-200 p-3">
        <div>
          <div className="font-medium">{"Billing"}</div>
          <div className="text-sm text-slate-500">{"No holds"}</div>
        </div>
        <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
          {"Operational"}
        </span>
      </div>
    </div>
  </div>
<div className="rounded-lg border border-slate-200 bg-white p-5">
    <div className="flex items-center gap-2">
      <ActivityIcon className="size-5 text-[var(--support-accent)]" />
      <h2 className="font-semibold">{"Recent activity"}</h2>
    </div>
    <div className="mt-4 grid gap-3">
      <div className="flex gap-3 text-sm">
        <GaugeIcon className="mt-0.5 size-4 shrink-0 text-slate-400" />
        <span className="text-slate-700">{"Retry queue increased for Salesforce connector"}</span>
      </div>
<div className="flex gap-3 text-sm">
        <GaugeIcon className="mt-0.5 size-4 shrink-0 text-slate-400" />
        <span className="text-slate-700">{"Incident INC-2479 opened for us-west sync workers"}</span>
      </div>
<div className="flex gap-3 text-sm">
        <GaugeIcon className="mt-0.5 size-4 shrink-0 text-slate-400" />
        <span className="text-slate-700">{"Acme Operations uploaded sync-error.log"}</span>
      </div>
    </div>
  </div>
  </div>
        </section>
      </div>
    </main>
  );
}
