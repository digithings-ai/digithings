"use client";

import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

/**
 * CommandPalette — the ⌘K command bar shell promoted from the design
 * reference (chrome/command-palette). The shell owns the chrome and the
 * interaction contract: overlay/backdrop, a document.body portal, the search
 * input row, the grouped listbox, the keyboard loop (↑/↓/Home/End/↵/esc,
 * focus held on the input) and the listbox ARIA wiring — `role="listbox"`
 * with `role="option"` children and `aria-activedescendant` on the listbox
 * (the pattern the olympus dashboard's palette was fixed to; preserved here).
 *
 * The CONSUMER owns everything data- and router-shaped: the `open` flag (and
 * whatever global shortcut toggles it — the shell binds no ⌘K), the grouped
 * item list — recomputed per keystroke when `groups` is a function of the
 * query — and per-item `onSelect` callbacks (router.push, theme toggles, …).
 * No router, data fetching, or filtering policy lives here.
 *
 * Query state is internal and resets on every open, synchronously on the
 * opening render, so a reopen never flashes the previous query. Enter or
 * click selects the active item: palette-level `onSelect(item)` fires, then
 * `item.onSelect()`, then `onClose()` unless `closeOnSelect={false}`.
 *
 * Wiring (in the consuming app's globals.css):
 *   @import "@digithings/web/styles/command-palette.css";
 *   @source "<path-to>/digiweb/web/src/components/command-palette";
 * Overlay stacking: the overlay's z-index reads var(--cp-z, 40) — set --cp-z
 * at the call site when the app's chrome stacks higher than the reference's.
 *
 * Two dresses (styles/command-palette.css):
 * - dress="reference" (default): the design-reference dress — mono rows,
 *   surface-mix panel, token scrim.
 * - dress="glass": the olympus dashboard's shipped ⌘K look, translated
 *   exactly — black/75 blurred scrim, term-bg panel (32rem, 12px radius),
 *   sans rows with accent-ring active state.
 */
export type CommandPaletteItem = {
  /** Stable identity — React key; option DOM ids are index-derived. */
  id: string;
  label: ReactNode;
  /** Optional muted second line under the label (the olympus "hint"). */
  description?: ReactNode;
  /** Fired when the row is chosen (Enter or click) — router.push lives here. */
  onSelect?: () => void;
  /** Optional right-edge keycap hint — "B", "⌘K". */
  kbd?: string;
  /** Livery scope class for the row (`accent-<livery>`) — colors the dot. */
  livery?: string;
  /** Show the leading livery dot (reference grammar). */
  dot?: boolean;
  /** Leading icon node — wins over `dot` when both are set. */
  icon?: ReactNode;
};

export type CommandPaletteGroup = {
  id?: string;
  /** Optional group heading; unlabeled groups render without `role="group"`. */
  label?: ReactNode;
  items: CommandPaletteItem[];
};

export type CommandPaletteProps = {
  /** Controlled visibility — the consumer owns the flag and its shortcut. */
  open: boolean;
  /** Fired by esc, the scrim, and (by default) after a selection. */
  onClose: () => void;
  /**
   * The grouped item list. Pass a function to recompute it per keystroke —
   * it receives the shell's current query verbatim (filtering policy is
   * entirely the consumer's).
   */
  groups: CommandPaletteGroup[] | ((query: string) => CommandPaletteGroup[]);
  /** Palette-level selection hook, fired before the item's own onSelect. */
  onSelect?: (item: CommandPaletteItem) => void;
  /** Close the palette after a selection (default true). */
  closeOnSelect?: boolean;
  placeholder?: string;
  /**
   * Footer key-hint legend: `true` renders the standard ↑↓ / ↵ / esc legend,
   * a node renders custom content inside `.cp-foot`, absent renders nothing.
   */
  footer?: ReactNode | boolean;
  /** Trailing input-row slot — defaults to an `esc` keycap. */
  inputTrailing?: ReactNode;
  /** Leading input-row slot — defaults to the built-in magnifier glyph. */
  inputLeading?: ReactNode;
  /**
   * Input `type` attribute (default "text"). Olympus ships type="search"
   * (native search-cancel affordance in WebKit/Chromium).
   */
  inputType?: string;
  /** Empty-results content; the function form receives the current query. */
  emptyMessage?: ReactNode | ((query: string) => ReactNode);
  /** Dialog aria-label (default "Command palette"). */
  ariaLabel?: string;
  /** Listbox aria-label (default "Commands"). */
  listLabel?: string;
  /** Input aria-label (default "Search commands"). */
  inputAriaLabel?: string;
  /** Extra class on the panel. */
  className?: string;
  /** Render into a document.body portal (default) or in place. */
  portal?: boolean;
  /** Visual dress — "reference" (default) or olympus's "glass". */
  dress?: "reference" | "glass";
};

const defaultEmpty = (query: string): ReactNode =>
  query ? <>No matches for “{query}”.</> : "No matches.";

export function CommandPalette({
  open,
  onClose,
  groups,
  onSelect,
  closeOnSelect = true,
  placeholder = "Type a command or search…",
  footer,
  inputTrailing,
  inputLeading,
  inputType = "text",
  emptyMessage,
  ariaLabel = "Command palette",
  listLabel = "Commands",
  inputAriaLabel = "Search commands",
  className,
  portal = true,
  dress = "reference",
}: CommandPaletteProps) {
  const baseId = useId();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [mounted, setMounted] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);

  // Reset synchronously on the opening render — a reopen never flashes the
  // previous query (React's adjust-state-during-render pattern).
  const [prevOpen, setPrevOpen] = useState(open);
  if (open !== prevOpen) {
    setPrevOpen(open);
    if (open) {
      setQuery("");
      setActive(0);
    }
  }

  useEffect(() => setMounted(true), []);

  const resolvedGroups = typeof groups === "function" ? groups(query) : groups;
  const flat = resolvedGroups.flatMap((g) => g.items);
  const count = flat.length;
  const activeIndex = count === 0 ? -1 : Math.min(active, count - 1);

  const select = (item: CommandPaletteItem) => {
    onSelect?.(item);
    item.onSelect?.();
    if (closeOnSelect) onClose();
  };

  // Refs keep one keydown listener per open, not one per keystroke.
  const flatRef = useRef(flat);
  const activeRef = useRef(activeIndex);
  const selectRef = useRef(select);
  const onCloseRef = useRef(onClose);
  useLayoutEffect(() => {
    flatRef.current = flat;
    activeRef.current = activeIndex;
    selectRef.current = select;
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCloseRef.current();
        return;
      }
      const len = flatRef.current.length;
      if (len === 0) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((i) => Math.min(i + 1, len - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((i) => Math.max(i - 1, 0));
      } else if (e.key === "Home") {
        e.preventDefault();
        setActive(0);
      } else if (e.key === "End") {
        e.preventDefault();
        setActive(len - 1);
      } else if (e.key === "Enter") {
        e.preventDefault();
        const idx = Math.min(Math.max(0, activeRef.current), len - 1);
        const item = flatRef.current[idx];
        if (item) selectRef.current(item);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Keep the active row in view as the keyboard walks the list.
  useLayoutEffect(() => {
    if (!open || activeIndex < 0 || !listRef.current) return;
    listRef.current
      .querySelector(`[data-cp-index="${activeIndex}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [open, activeIndex, query]);

  if (!open) return null;

  const empty =
    typeof emptyMessage === "function"
      ? emptyMessage(query)
      : emptyMessage ?? defaultEmpty(query);

  let flatIndex = -1;
  const palette = (
    <div
      className={`cp-overlay${dress === "glass" ? " cp-overlay--glass" : ""}`}
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel}
    >
      <div className="cp-scrim" onClick={onClose} aria-hidden="true" />
      <div className={`cp-panel${className ? ` ${className}` : ""}`}>
        <div className="cp-input-row">
          {inputLeading !== undefined ? (
            inputLeading
          ) : (
            <span className="cp-search-glyph" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                width="16"
                height="16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
              >
                <circle cx="11" cy="11" r="7" />
                <path d="M20 20l-3.5-3.5" strokeLinecap="round" />
              </svg>
            </span>
          )}
          <input
            className="cp-input"
            type={inputType}
            placeholder={placeholder}
            value={query}
            autoFocus
            autoComplete="off"
            spellCheck={false}
            aria-label={inputAriaLabel}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
          />
          {inputTrailing !== undefined ? inputTrailing : <kbd className="cp-kbd">esc</kbd>}
        </div>

        <div
          ref={listRef}
          className="cp-results"
          role="listbox"
          aria-label={listLabel}
          aria-activedescendant={activeIndex >= 0 ? `${baseId}-opt-${activeIndex}` : undefined}
        >
          {count === 0 ? (
            <p className="cp-empty" role="presentation">
              {empty}
            </p>
          ) : (
            resolvedGroups.map((g, gi) => {
              if (g.items.length === 0) return null;
              const labelId = g.label != null ? `${baseId}-grp-${gi}` : undefined;
              const rows = g.items.map((item) => {
                flatIndex += 1;
                const idx = flatIndex;
                const on = idx === activeIndex;
                return (
                  <div
                    key={item.id}
                    id={`${baseId}-opt-${idx}`}
                    role="option"
                    aria-selected={on}
                    data-cp-index={idx}
                    className={`cp-row${on ? " on" : ""}${item.livery ? ` accent-${item.livery}` : ""}`}
                    onClick={() => select(item)}
                    onMouseEnter={() => setActive(idx)}
                  >
                    {item.icon ? (
                      <span className="cp-icon" aria-hidden="true">
                        {item.icon}
                      </span>
                    ) : item.dot ? (
                      <span className="cp-dot" aria-hidden="true" />
                    ) : null}
                    <span className="cp-label">
                      {item.label}
                      {item.description != null ? (
                        <span className="cp-desc">{item.description}</span>
                      ) : null}
                    </span>
                    {item.kbd ? <kbd className="cp-kbd cp-row-key">{item.kbd}</kbd> : null}
                  </div>
                );
              });
              return g.label != null ? (
                <div key={g.id ?? gi} className="cp-group" role="group" aria-labelledby={labelId}>
                  <p className="cp-group-label" id={labelId} role="presentation">
                    {g.label}
                  </p>
                  {rows}
                </div>
              ) : (
                <div key={g.id ?? gi} className="cp-group" role="presentation">
                  {rows}
                </div>
              );
            })
          )}
        </div>

        {footer === true ? (
          <div className="cp-foot" aria-hidden="true">
            <span>
              <kbd className="cp-kbd">↑</kbd>
              <kbd className="cp-kbd">↓</kbd> navigate
            </span>
            <span>
              <kbd className="cp-kbd">↵</kbd> open
            </span>
            <span>
              <kbd className="cp-kbd">esc</kbd> close
            </span>
          </div>
        ) : footer ? (
          <div className="cp-foot" aria-hidden="true">
            {footer}
          </div>
        ) : null}
      </div>
    </div>
  );

  if (!portal) return palette;
  if (!mounted) return null;
  return createPortal(palette, document.body);
}
