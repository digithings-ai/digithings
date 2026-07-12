"use client";
import { useState } from "react";
import {
  TerminalManifest,
  modules,
  type ModuleNode,
  type TerminalManifestRow,
} from "@digithings/web";
import { writeHandoff } from "@/lib/chatHandoff";

/**
 * Terminal-manifest display of the ten DigiThings modules — a `digithings ps`
 * process list rendered by the shared <TerminalManifest> primitive
 * (@digithings/web, promoted from this component in #1415). Each row: a
 * status dot (online vs roadmap), the lowercase two-tone name (`digi` ink +
 * suffix accent), and the role.
 *
 * Clicking a row runs `digithings show <module>` and the module's description
 * (the prose that used to live on its own page) types out live at the cursor,
 * terminal-style — so the per-module pages fold into the manifest itself.
 * prefers-reduced-motion reveals the output instantly (primitive behavior).
 * Renders from the shared `modules` data (single source of truth), sorted by
 * graphOrder. Selection is controlled here so the "ask digichat" footer knows
 * which module to hand off.
 */
function buildOutput(m: ModuleNode): string {
  const stack = m.stack.map((s) => s.name).join("  ·  ");
  return [m.tagline, "", ...m.summary, "", "stack   " + stack].join("\n");
}

/** Hand off to the full /chat page — about the selected module, or a general
 * overview when nothing is selected. */
function askAbout(m: ModuleNode | null): void {
  const q = m ? `What does ${m.id} do, and how do I use it?` : "Give me an overview of the digithings stack.";
  writeHandoff([], q);
  window.location.href = "/chat";
}

export function ModuleManifest() {
  const mods = [...modules].sort((a, b) => a.graphOrder - b.graphOrder);
  const online = mods.filter((m) => m.tier !== "roadmap").length;
  const road = mods.length - online;

  const rows: TerminalManifestRow[] = mods.map((m) => ({
    id: m.id,
    name: m.id,
    status: m.tier === "roadmap" ? "roadmap" : "online",
    blurb: m.role,
    detail: buildOutput(m),
  }));

  const [sel, setSel] = useState<string | null>(null);
  const selMod = sel ? (mods.find((m) => m.id === sel) ?? null) : null;

  return (
    <TerminalManifest
      className="mx-auto max-w-[980px]"
      command="digithings ps"
      meta={`· ${online} online · ${road} on the roadmap`}
      rows={rows}
      namePrefix="digi"
      hint="select a module"
      selectedId={sel}
      onSelect={setSel}
      aria-label="digithings module manifest"
      footer={
        <button
          type="button"
          className="mt-auto cursor-pointer self-end rounded-[7px] border border-hair bg-transparent px-[0.6rem] py-[0.3rem] font-mono text-[0.78rem] text-ink-soft transition-colors hover:bg-accent-weak hover:text-ink"
          onClick={() => askAbout(selMod)}
        >
          ask <span className="text-ink">digi</span>
          <span className="text-accent">chat</span> →
        </button>
      }
    />
  );
}
