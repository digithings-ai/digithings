"use client";
import { useState } from "react";
import {
  TerminalManifest,
  modules,
  type ModuleNode,
  type TerminalManifestRow,
} from "@digithings/ui";
import { Button } from "@digithings/ui/ui";
import { writeHandoff } from "@/lib/chatHandoff";
import { moduleActivity } from "@/lib/repoActivity";

/**
 * Terminal manifest of the modules, rendered by the shared <TerminalManifest>
 * primitive — each row a status dot (online vs roadmap), the lowercase
 * two-tone name and the role. Selecting a row types the module's detail at the
 * cursor; the footer hands the selected module to digichat.
 *
 * Client island because selection and the handoff are interactive; the page
 * itself stays a server component. Renders from the shared `modules` registry
 * (single source of truth), sorted by graphOrder.
 */
function buildOutput(m: ModuleNode): string {
  const stack = m.stack.map((s) => s.name).join("  ·  ");
  const activity = moduleActivity(m.id);
  return [
    m.tagline,
    "",
    ...m.summary,
    "",
    "stack   " + stack,
    ...(activity ? ["repo    " + activity] : []),
  ].join("\n");
}

/** Hand off to the full /chat page — about the selected module, or a general
 * overview when nothing is selected. */
function askAbout(m: ModuleNode | null): void {
  const q = m
    ? `What does ${m.id} do, and how do I use it?`
    : "Give me an overview of the digithings stack.";
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
      prompt="//"
      command="modules"
      meta={`· ${online} online · ${road} on the roadmap`}
      rows={rows}
      namePrefix="digi"
      hint="select a module"
      selectedId={sel}
      onSelect={setSel}
      aria-label="digithings module manifest"
      footer={
        <Button
          type="button"
          variant="outline"
          size="xs"
          className="mt-auto self-end font-mono text-[0.78rem] text-ink-soft"
          onClick={() => askAbout(selMod)}
        >
          ask <span className="text-ink">digi</span>
          <span className="text-accent">chat</span> →
        </Button>
      }
    />
  );
}
