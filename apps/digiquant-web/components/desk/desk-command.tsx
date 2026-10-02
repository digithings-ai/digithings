"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Button } from "@digithings/ui/ui";
import { searchDeskPages } from "./desk-command-search";

/**
 * Path field for the web desk. `/` or ⌘K focuses it, typing filters pages,
 * ↑/↓ chooses, Enter opens the desk href, Esc cancels.
 */
export function DeskCommand({ pathname }: { pathname: string }) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState<string | null>(null);
  const [sel, setSel] = useState(0);
  const editing = q !== null;
  const hits = editing ? searchDeskPages(q).slice(0, 8) : [];

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target;
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable);
      const bare = !e.metaKey && !e.ctrlKey && !e.altKey;
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !typing && bare)) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const go = (path: string) => {
    const href = searchDeskPages("").find((hit) => hit.path === path)?.href;
    if (!href) return;
    setQ(null);
    setSel(0);
    input.current?.blur();
    router.push(href);
  };

  return (
    <div className="cmd">
      <input
        ref={input}
        className="cmd-in"
        spellCheck={false}
        aria-label="Go to page"
        aria-expanded={editing && hits.length > 0}
        aria-controls={editing && hits.length > 0 ? "cmd-list" : undefined}
        aria-autocomplete="list"
        aria-haspopup="listbox"
        aria-activedescendant={editing && hits[sel] ? `cmd-opt-${sel}` : undefined}
        role="combobox"
        value={editing ? q : pathname}
        placeholder="/ go to…"
        onFocus={(e) => {
          setQ("");
          setSel(0);
          e.currentTarget.select();
        }}
        onBlur={() => setTimeout(() => setQ(null), 120)}
        onChange={(e) => {
          setQ(e.target.value);
          setSel(0);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setSel((s) => Math.min(s + 1, Math.max(hits.length - 1, 0)));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setSel((s) => Math.max(s - 1, 0));
          } else if (e.key === "Enter" && hits[sel]) go(hits[sel].path);
          else if (e.key === "Escape") {
            setQ(null);
            setSel(0);
            e.currentTarget.blur();
          }
        }}
      />
      <span className="sr" role="status" aria-live="polite">
        {editing && q ? (hits.length ? `${hits.length} pages` : "no matching pages") : ""}
      </span>
      {editing && hits.length > 0 ? (
        <ul id="cmd-list" role="listbox" className="cmd-list">
          {hits.map((hit, i) => (
            <li key={hit.path} id={`cmd-opt-${i}`} role="option" aria-selected={i === sel} className={i === sel ? "on" : undefined}>
              <Button
                type="button"
                variant="ghost"
                className="cmd-hit"
                onMouseDown={(e) => {
                  e.preventDefault();
                  go(hit.path);
                }}
              >
                <span>{hit.href}</span>
                <span className="mute">{hit.label}</span>
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
