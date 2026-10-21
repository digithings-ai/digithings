"use client";

/**
 * Compact mode + palette picker. Replaces the light/dark toggle on surfaces
 * that opt in. The control lives in the kit so the cursor and the popover
 * are not re-implemented per app.
 */
import { useEffect, useId, useRef, useState, type CSSProperties } from "react";
import { PALETTE_IDS } from "../theme/palette-registry";
import { IconButton } from "../ui/icon-button";
import { useTheme, type ThemePreference } from "./ThemeProvider";

const MODES: readonly { id: ThemePreference; label: string }[] = [
  { id: "dark", label: "Dark" },
  { id: "light", label: "Light" },
  { id: "auto", label: "Auto" },
];

const panelStyle: CSSProperties = {
  position: "absolute",
  top: "calc(100% + 4px)",
  right: 0,
  zIndex: 80,
  width: "16rem",
  maxHeight: "22rem",
  overflow: "auto",
  background: "var(--surface)",
  color: "var(--ink)",
  border: "1px solid var(--hair)",
  padding: "0.5rem",
};

const rowStyle: CSSProperties = {
  display: "flex",
  width: "100%",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "0.5rem",
  cursor: "pointer",
  background: "transparent",
  color: "inherit",
  border: 0,
  padding: "0.35rem 0.25rem",
  textAlign: "start",
  font: "inherit",
};

export function ThemePicker({ className }: { className?: string }) {
  const { theme, preference, setTheme, palette, setPalette } = useTheme();
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState<"mode" | "palette">("mode");
  const rootRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="dt-theme-picker" style={{ position: "relative" }}>
      <IconButton
        type="button"
        aria-label="Colour theme"
        aria-expanded={open}
        aria-controls={panelId}
        title={`Theme: ${preference} · ${palette}`}
        className={className ?? "theme-toggle"}
        onClick={() => {
          setPage("mode");
          setOpen((value) => !value);
        }}
      >
        {theme === "dark" ? (
          <svg
            viewBox="0 0 24 24"
            width="17"
            height="17"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          >
            <circle cx="12" cy="12" r="4.2" />
            <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8" />
          </svg>
        ) : (
          <svg
            viewBox="0 0 24 24"
            width="17"
            height="17"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinejoin="round"
          >
            <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />
          </svg>
        )}
      </IconButton>
      {open ? (
        <div id={panelId} role="dialog" aria-label="Theme" style={panelStyle}>
          {page === "mode" ? (
            <div>
              <p style={{ margin: "0 0 0.25rem", color: "var(--ink-mute)", fontSize: "0.75rem" }}>
                Mode · {preference}
              </p>
              {MODES.map((mode) => (
                <button
                  key={mode.id}
                  type="button"
                  className="cursor-pointer"
                  aria-pressed={preference === mode.id}
                  style={rowStyle}
                  onClick={() => setTheme(mode.id)}
                >
                  <span>{mode.label}</span>
                  {preference === mode.id ? <span aria-hidden="true">●</span> : null}
                </button>
              ))}
              <button
                type="button"
                className="cursor-pointer"
                style={{ ...rowStyle, borderTop: "1px solid var(--hair)", marginTop: "0.25rem" }}
                onClick={() => setPage("palette")}
              >
                <span>Palette</span>
                <span style={{ color: "var(--ink-mute)" }}>{palette}</span>
              </button>
            </div>
          ) : (
            <div>
              <button
                type="button"
                className="cursor-pointer"
                style={{ ...rowStyle, color: "var(--ink-mute)" }}
                onClick={() => setPage("mode")}
              >
                Back
              </button>
              <button
                type="button"
                className="cursor-pointer"
                aria-pressed={palette === "default"}
                style={rowStyle}
                onClick={() => setPalette("default")}
              >
                <span>default</span>
                {palette === "default" ? <span aria-hidden="true">●</span> : null}
              </button>
              {PALETTE_IDS.map((id) => (
                <button
                  key={id}
                  type="button"
                  className="cursor-pointer"
                  aria-pressed={palette === id}
                  style={rowStyle}
                  onClick={() => setPalette(id)}
                >
                  <span>{id}</span>
                  {palette === id ? <span aria-hidden="true">●</span> : null}
                </button>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
