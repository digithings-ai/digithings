"use client";
import { useEffect, useRef, useState } from "react";

import { cn } from "../../lib/utils";
import { Kbd } from "../../ui/kbd";
import { SearchBar } from "../../ui/search-bar";
import type { DocsNavItem } from "./DocsLayout";

/**
 * Docs search — the bordered `⌘K` affordance over a page's own headings.
 * There is no index and no dependency: the caller hands over the same
 * `DocsNavItem[]` the rail renders, and the field filters them on the client.
 * `⌘K` / `Ctrl-K` focuses the field from anywhere on the page (D1, #4429).
 */

/** Case-insensitive match over an item's label, falling back to its id. */
export function filterDocsItems(items: DocsNavItem[], query: string): DocsNavItem[] {
  const needle = query.trim().toLowerCase();
  if (needle === "") return [];
  return items.filter((item) =>
    typeof item.label === "string"
      ? item.label.toLowerCase().includes(needle)
      : item.id.toLowerCase().includes(needle),
  );
}

export interface DocsSearchProps {
  items: DocsNavItem[];
  /** Accessible name for the field. */
  label?: string;
  placeholder?: string;
  className?: string;
}

export function DocsSearch({
  items,
  label = "Search sections",
  placeholder = "Search",
  className,
}: DocsSearchProps) {
  const [query, setQuery] = useState("");
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        wrapRef.current?.querySelector("input")?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const matches = filterDocsItems(items, query);

  return (
    <div ref={wrapRef} className={cn("flex flex-col items-start gap-[0.5rem]", className)}>
      <SearchBar
        value={query}
        onChange={setQuery}
        aria-label={label}
        placeholder={placeholder}
        hint={<Kbd>⌘K</Kbd>}
      />
      {query.trim() !== "" && (
        <ul className="m-0 grid w-[min(100%,26rem)] list-none gap-0 border border-hair p-0">
          {matches.length > 0 ? (
            matches.map((item) => (
              <li key={item.id}>
                <a
                  href={`#${item.id}`}
                  className="block px-[0.7rem] py-[0.45rem] font-mono text-[0.82rem] text-ink-soft no-underline transition-colors duration-150 ease-brand hover:bg-accent-weak hover:text-ink"
                >
                  {item.label}
                </a>
              </li>
            ))
          ) : (
            <li className="px-[0.7rem] py-[0.45rem] font-mono text-[0.82rem] text-ink-mute">
              no section matches
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
