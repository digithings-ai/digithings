'use client';

import { useRouter } from 'next/navigation';
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { searchPages } from '@/lib/nav';
import { useAccess } from './Access';

export type CommandLineHandle = { focus: () => void };

/**
 * The top chrome is the path. Focus it (`/` or ⌘K), type to filter pages,
 * ↑/↓ to choose, Enter to go, Esc to cancel.
 */
export const CommandLine = forwardRef<CommandLineHandle, { pathname: string }>(function CommandLine({ pathname }, ref) {
  const router = useRouter();
  const { pages } = useAccess();
  const input = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState<string | null>(null); // null = showing the current path
  const [sel, setSel] = useState(0);

  useImperativeHandle(ref, () => ({ focus: () => input.current?.focus() }));

  const editing = q !== null;
  const hits = editing ? searchPages(q, pages).slice(0, 8) : [];

  useEffect(() => setSel(0), [q]);

  const go = (path: string) => {
    setQ(null);
    input.current?.blur();
    router.push(path);
  };

  return (
    <div className="cmd">
      <input
        ref={input}
        className="cmd-in"
        spellCheck={false}
        aria-label="Go to page"
        aria-expanded={editing && hits.length > 0}
        aria-controls={editing && hits.length > 0 ? 'cmd-list' : undefined}
        aria-autocomplete="list"
        aria-haspopup="listbox"
        aria-activedescendant={editing && hits[sel] ? `cmd-opt-${sel}` : undefined}
        role="combobox"
        value={editing ? q : pathname}
        placeholder="/ go to…"
        onFocus={(e) => { setQ(''); e.currentTarget.select(); }}
        onBlur={() => setTimeout(() => setQ(null), 120)}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(s + 1, hits.length - 1)); }
          else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
          else if (e.key === 'Enter' && hits[sel]) go(hits[sel].path);
          else if (e.key === 'Escape') { setQ(null); e.currentTarget.blur(); }
        }}
      />
      <span className="sr" role="status" aria-live="polite">{editing && q ? (hits.length ? `${hits.length} pages` : 'no matching pages') : ''}</span>
      {editing && hits.length > 0 ? (
        <ul id="cmd-list" role="listbox" className="cmd-list">
          {hits.map((h, i) => (
            <li key={h.path} id={`cmd-opt-${i}`} role="option" aria-selected={i === sel} className={i === sel ? 'on' : undefined} onMouseDown={(e) => { e.preventDefault(); go(h.path); }}>
              <span>{h.path}</span>
              <span className="mute">{h.label}{h.lock ? ` [${h.lock}]` : ''}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
});
