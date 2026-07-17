"use client";

import { useEffect, useState } from "react";
import { CommandPalette, type CommandPaletteGroup } from "@digithings/web";

/**
 * Command palette — the dev-tool ⌘K signature: a fuzzy command bar over a
 * blurred page, opened by keystroke or the trigger button. Actions are grouped,
 * each row carries a livery dot and a shortcut, and arrow keys drive a flat
 * active index across the groups. Rendered into a portal on the body.
 * Consumes the shared <CommandPalette/> shell from @digithings/web — the shell
 * owns the overlay, input row, grouped listbox, keyboard loop and ARIA; this
 * specimen owns the open flag (and its ⌘K binding) plus the demo command
 * list, recomputed per query through the `groups` function.
 */
type Command = { id: string; label: string; hint: string; livery?: string };

const COMMAND_GROUPS: { label: string; commands: Command[] }[] = [
  {
    label: "Actions",
    commands: [
      { id: "backtest", label: "Run a backtest", hint: "B", livery: "digiquant" },
      { id: "chat", label: "Ask digichat", hint: "C", livery: "digichat" },
      { id: "key", label: "Issue an API key", hint: "K", livery: "digikey" },
      { id: "search", label: "Search the corpus", hint: "/", livery: "digisearch" },
    ],
  },
  {
    label: "Navigate",
    commands: [
      { id: "olympus", label: "Open olympus", hint: "O", livery: "atlas" },
      { id: "vault", label: "Open the vault", hint: "V", livery: "digivault" },
      { id: "changelog", label: "View changelog", hint: "L" },
      { id: "theme", label: "Toggle theme", hint: "T" },
    ],
  },
];

const groupsFor = (query: string): CommandPaletteGroup[] =>
  COMMAND_GROUPS.map((g) => ({
    label: g.label,
    items: g.commands
      .filter((c) => c.label.toLowerCase().includes(query.toLowerCase()))
      .map((c) => ({ id: c.id, label: c.label, kbd: c.hint, livery: c.livery, dot: true })),
  })).filter((g) => g.items.length > 0);

export function CommandPaletteReference() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <section className="section-block command-palette">
      <p className="kicker">{"// command palette"}</p>
      <h2 className="title">Everything, a keystroke away.</h2>
      <p className="section-copy">
        The dev-tool signature: <kbd className="kbd">⌘</kbd>
        <kbd className="kbd">K</kbd> opens a fuzzy command bar over a blurred page. Grouped actions,
        a livery dot per module, a shortcut on each row, and arrow-key navigation. Try it — press
        ⌘K (or Ctrl K), or the button.
      </p>

      <button type="button" className="cp-trigger" onClick={() => setOpen(true)}>
        <span>Search commands…</span>
        <span className="inline-flex gap-[0.2rem]">
          <kbd className="kbd">⌘</kbd>
          <kbd className="kbd">K</kbd>
        </span>
      </button>

      <CommandPalette
        open={open}
        onClose={() => setOpen(false)}
        groups={groupsFor}
        footer
        emptyMessage={(q) => <>No commands match “{q}”.</>}
      />
    </section>
  );
}
