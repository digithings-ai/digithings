"use client";

import { useRef, useState } from "react";

/**
 * Tags / chips input — the multi-select filter. Type and Enter (or comma) to
 * add a chip, × or Backspace-on-empty to remove, click a suggestion to add it.
 * Chips wear a hairline pill; the field lights the accent on focus. Keyboard-
 * complete and dedup-guarded. Accent reads under the monochrome default.
 */
const SUGGESTIONS = ["momentum", "mean-reversion", "carry", "ETH-USD", "BTC-PERP", "PF>2", "live"];

export function TagsInputReference() {
  const [tags, setTags] = useState<string[]>(["momentum", "ETH-USD"]);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  const add = (raw: string) => {
    const t = raw.trim().replace(/,$/, "");
    if (t && !tags.includes(t)) setTags((prev) => [...prev, t]);
    setDraft("");
  };

  const removeAt = (i: number) => setTags((prev) => prev.filter((_, idx) => idx !== i));

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add(draft);
    } else if (e.key === "Backspace" && draft === "" && tags.length) {
      removeAt(tags.length - 1);
    }
  };

  const remaining = SUGGESTIONS.filter((s) => !tags.includes(s));

  return (
    <section className="section-block">
      <p className="kicker">{"// tags input"}</p>
      <h2 className="title">Filters, as chips.</h2>
      <p className="section-copy">
        A multi-select built from chips: type and Enter (or a comma) to add, × or Backspace to
        remove, or pull from the suggestions. Duplicates are dropped, the field lights the accent on
        focus, and every chip carries its own remove control.
      </p>

      <div className="tg-field" onClick={() => inputRef.current?.focus()}>
        {tags.map((t, i) => (
          <span className="tg-chip" key={t}>
            {t}
            <button
              type="button"
              className="tg-x"
              aria-label={`Remove ${t}`}
              onClick={(e) => {
                e.stopPropagation();
                removeAt(i);
              }}
            >
              <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          // flex-1 only on the empty field (so the placeholder gets full width);
          // once chips exist the input sits compact after the last one instead of
          // stretching across the row's empty trailing space.
          className={`min-w-[7rem] border-none bg-transparent p-[0.2rem] font-mono text-[0.8rem] text-ink outline-none placeholder:text-ink-mute${
            tags.length ? "" : " flex-1"
          }`}
          value={draft}
          placeholder={tags.length ? "" : "filter strategies…"}
          aria-label="Add a filter tag"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
        />
      </div>

      {remaining.length ? (
        <div className="mt-[0.7rem] flex flex-wrap items-center gap-[0.4rem]">
          <span className="mr-[0.2rem] font-mono text-[0.56rem] uppercase tracking-[0.1em] text-ink-mute">
            suggestions
          </span>
          {remaining.map((s) => (
            <button key={s} type="button" className="tg-suggest-chip" onClick={() => add(s)}>
              + {s}
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}
