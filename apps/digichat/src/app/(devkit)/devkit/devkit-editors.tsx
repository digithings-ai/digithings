"use client";

import { useEffect, useId, useRef, useState } from "react";
import { THREAD_SKINS } from "@digithings/ui/chat/skins";
import {
  Button,
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Field,
  IconButton,
  Input,
  SegmentedControl,
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
  Switch,
  Textarea,
} from "@digithings/ui/ui";
import { FEATURED_LANGUAGE_CODES } from "@/lib/languages";
import type { DigichatDeployment } from "@/lib/deploy-config/schema";
import { CONTRAST_MINIMUM, contrast } from "./devkit-contrast";
import {
  appendListItem,
  applyAll,
  deleteKey,
  deleteListItemField,
  isValidSlug,
  removeListItem,
  secretState,
  secretStateInList,
  setBoolean,
  setListItemScalar,
  setScalar,
  setStringList,
  type SecretState,
  type EntryDraft,
  type TextEdit,
} from "./draft";

/** Commit one text edit into the draft; returns whether it applied. */
export type EditorsCommit = (edit: TextEdit) => boolean;

/**
 * Spec §2 regrouping map (titles verbatim): the 3 groups are the only
 * collapsible level; the 8 sections render inside their group as
 * always-expanded subgroups, each exactly once.
 */
const GROUPS = [
  { id: "basics", label: "Basics", sections: ["Identity", "Features", "Models"] },
  { id: "appearance", label: "Appearance", sections: ["Appearance"] },
  { id: "advanced", label: "Advanced", sections: ["Backend", "Tools", "MCP servers", "Gate"] },
] as const;

type SectionTitle = (typeof GROUPS)[number]["sections"][number];

/** Stable anchor id per subgroup; nav targets the 3 group ids directly. */
function sectionAnchorId(title: SectionTitle): string {
  return `devkit-section-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

/**
 * Scroll-spy pick (spec §1): the foremost anchor at/above the active band
 * wins — the nearest crossed anchor (greatest top still <= 0). When no
 * anchor has crossed yet (top of the list), the foremost entry below the
 * line wins. Empty → null (the observer then keeps the current group).
 */
export function visibleGroupFromEntries(
  entries: Array<{ id: string; top: number }>,
): string | null {
  if (entries.length === 0) return null;
  let above: { id: string; top: number } | null = null;
  let below: { id: string; top: number } | null = null;
  for (const entry of entries) {
    if (entry.top <= 0) {
      if (above === null || entry.top > above.top) above = entry;
    } else if (below === null || entry.top < below.top) {
      below = entry;
    }
  }
  return (above ?? below)?.id ?? null;
}

/**
 * Scroll-spy state step (spec §1): given the open group, the manually-closed
 * group (if any), and the newly elected visible group, returns the next
 * open/suppressed pair. The observer may change which single group is open
 * but never collapses: a null vote keeps everything, and a same-id
 * re-election after a manual close is suppressed until a different group
 * becomes visible (which releases the suppression).
 *
 * `navTarget` arms the settle hold for a nav click: while armed, a vote for
 * any other group is stale mid-scroll geometry (the clicked anchor cannot
 * cross root-top when max-scroll clamps it below the band) and must not yank
 * the clicked group away. A vote for the target itself releases the hold.
 */
export function applyScrollSpyVote(
  open: string | null,
  manualClosed: string | null,
  visible: string | null,
  navTarget?: string | null,
): { open: string | null; manualClosed: string | null } {
  if (navTarget) {
    if (visible === navTarget) return { open: navTarget, manualClosed: null };
    return { open: navTarget, manualClosed };
  }
  if (visible === null) return { open, manualClosed };
  if (manualClosed !== null && visible === manualClosed) return { open, manualClosed };
  return { open: visible, manualClosed: null };
}

export function TextRow({
  label,
  value,
  placeholder,
  hint,
  required,
  onCommit,
  onClear,
}: {
  label: string;
  value: string | undefined;
  placeholder?: string;
  hint?: string;
  /** Required fields revert on empty instead of committing. */
  required?: boolean;
  /** Returns whether the commit applied; the row reverts its display on false. */
  onCommit: (v: string) => boolean;
  onClear?: () => void;
}) {
  const current = value ?? "";
  return (
    <span className="flex gap-1">
      <Field label={label} hint={hint} className="min-w-0 flex-1">
        <Input
          dress="chat"
          // Remount on committed-value change: uncontrolled inputs ignore
          // later defaultValue props, which both leaves stale text on screen
          // and trips Base UI's uncontrolled-FieldControl default-change
          // error. Commits land on blur/Enter (unfocused), so the remount
          // never steals focus; refused commits keep `current` and the
          // revert path below still applies.
          key={current}
          defaultValue={current}
          placeholder={placeholder}
          spellCheck={false}
          className="min-w-0 flex-1"
          onBlur={(e) => {
            const next = e.target.value;
            if (next === current) return;
            if (next === "" && required) {
              e.target.value = current; // required — revert, never write ""
              return;
            }
            if (!onCommit(next)) {
              e.target.value = current; // refused — revert, never diverge
            }
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
          }}
        />
      </Field>
      {onClear && current !== "" ? (
        <IconButton onClick={onClear} aria-label={`Clear ${label}`}>
          ✕
        </IconButton>
      ) : null}
    </span>
  );
}

export function BoolRow({
  label,
  checked,
  hint,
  onCommit,
}: {
  label: string;
  checked: boolean;
  hint?: string;
  onCommit: (v: boolean) => boolean;
}) {
  return (
    <Field label={label} hint={hint}>
      <Switch
        checked={checked}
        onCheckedChange={(next) => {
          if (!onCommit(next)) {
            // Refused: controlled value prop never changed, so the
            // primitive snaps back on re-render — no DOM write needed.
          }
        }}
      />
    </Field>
  );
}

/** One labeled option group inside a SelectRow popup (specimen GROUPS map shape). */
export type SelectOptionGroup = {
  label: string;
  options: readonly string[];
};

export function SelectRow({
  label,
  value,
  options,
  groups,
  hint,
  onCommit,
}: {
  label: string;
  value: string;
  hint?: string;
  onCommit: (v: string) => boolean;
} & (
  | { options: readonly string[]; groups?: undefined }
  | { options?: undefined; groups: readonly SelectOptionGroup[] }
)) {
  return (
    <Field label={label} hint={hint}>
      <Select
        value={value}
        onValueChange={(v) => {
          if (v != null) onCommit(v);
        }}
      >
        <SelectTrigger aria-label={label}>
          <SelectValue placeholder={`Choose ${label}`} />
        </SelectTrigger>
        <SelectContent>
          {groups
            ? groups.map((g, i) => (
                <SelectGroup key={g.label}>
                  {i > 0 ? <SelectSeparator /> : null}
                  <SelectLabel>{g.label}</SelectLabel>
                  {g.options.map((o) => (
                    <SelectItem key={o} value={o}>
                      {o}
                    </SelectItem>
                  ))}
                </SelectGroup>
              ))
            : (
                <SelectGroup>
                  {options.map((o) => (
                    <SelectItem key={o} value={o}>
                      {o}
                    </SelectItem>
                  ))}
                </SelectGroup>
              )}
        </SelectContent>
      </Select>
    </Field>
  );
}

/** Short static single-token sets: segmented group pattern, never nested in Field. */
export function SegRow({
  label,
  value,
  options,
  hint,
  onCommit,
}: {
  label: string;
  value: string;
  options: readonly string[];
  hint?: string;
  onCommit: (v: string) => boolean;
}) {
  const labelId = useId();
  const hintId = useId();
  return (
    <div className="grid min-w-0 gap-[0.35rem]">
      <span id={labelId} className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">
        {label}
      </span>
      <SegmentedControl
        options={options}
        aria-labelledby={labelId}
        aria-describedby={hint ? hintId : undefined}
        value={value}
        onChange={(v) => {
          onCommit(v);
        }}
      />
      {hint ? (
        <span id={hintId} className="font-mono text-[0.6rem] text-ink-mute">
          {hint}
        </span>
      ) : null}
    </div>
  );
}

/** Optional boolean: inherit (key absent) / on / off. */
export function TriRow({
  label,
  value,
  hint,
  onCommit,
}: {
  label: string;
  value: boolean | undefined;
  hint?: string;
  onCommit: (v: boolean | undefined) => boolean;
}) {
  const current = value === undefined ? "inherit" : value ? "on" : "off";
  const labelId = useId();
  const hintId = useId();
  return (
    <div className="grid min-w-0 gap-[0.35rem]">
      <span id={labelId} className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">
        {label}
      </span>
      <SegmentedControl
        options={["inherit", "on", "off"]}
        aria-labelledby={labelId}
        aria-describedby={hint ? hintId : undefined}
        value={current}
        onChange={(v) => {
          onCommit(v === "inherit" ? undefined : v === "on");
        }}
      />
      {hint ? (
        <span id={hintId} className="font-mono text-[0.6rem] text-ink-mute">
          {hint}
        </span>
      ) : null}
    </div>
  );
}

export function TextListRow({
  label,
  values,
  hint,
  onCommit,
}: {
  label: string;
  values: string[];
  hint?: string;
  onCommit: (lines: string[]) => boolean;
}) {
  const current = values.join("\n");
  return (
    <Field label={label} hint={hint}>
      <Textarea
        rows={3}
        // Same remount contract as TextRow: uncontrolled defaultValue must be
        // fresh at mount, never changed on a mounted instance.
        key={current}
        defaultValue={current}
        spellCheck={false}
        placeholder="one per line"
        onBlur={(e) => {
          if (e.target.value === current) return;
          if (
            !onCommit(
              e.target.value
                .split("\n")
                .map((l) => l.trim())
                .filter((l) => l !== ""),
            )
          ) {
            e.target.value = current; // refused — revert, never diverge
          }
        }}
      />
    </Field>
  );
}

/** Masked secret row: the value is never displayed, only preserved/replaced. */
export function SecretRow({
  label,
  state,
  hint,
  onReplace,
  onClear,
}: {
  label: string;
  state: SecretState;
  hint?: string;
  onReplace: (v: string) => boolean;
  onClear?: () => void;
}) {
  const [replacing, setReplacing] = useState(false);
  const [val, setVal] = useState("");
  const masked =
    state === "absent"
      ? "not set"
      : state === "sentinel"
        ? "•••••• (preserved from file)"
        : "•••••• (custom value — never shown)";
  const trySet = () => {
    if (val === "") return;
    if (!onReplace(val)) return; // refused — stay open, keep value
    setVal("");
    setReplacing(false);
  };
  const cancel = () => {
    setVal("");
    setReplacing(false);
  };
  if (replacing) {
    return (
      <span className="flex gap-1">
        <Field label={label} hint={hint} className="min-w-0 flex-1">
          <Input
            dress="chat"
            type="password"
            value={val}
            autoFocus
            placeholder="new secret value"
            aria-label="New secret value"
            spellCheck={false}
            className="min-w-0 flex-1"
            onChange={(e) => setVal(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") trySet();
              if (e.key === "Escape") cancel();
            }}
          />
        </Field>
        <Button type="button" dress="chat" disabled={val === ""} onClick={trySet}>
          Set
        </Button>
        <Button type="button" dress="chat" onClick={cancel}>
          Cancel
        </Button>
      </span>
    );
  }
  return (
    <div className="grid min-w-0 gap-[0.35rem]">
      <span className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">
        {label}
      </span>
      <span className="flex items-center gap-1">
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">
          {masked}
        </span>
        <Button type="button" dress="chat" onClick={() => setReplacing(true)}>
          {state === "absent" ? "Add" : "Replace"}
        </Button>
        {onClear && state !== "absent" ? (
          <IconButton title={`Clear ${label}`} aria-label={`Clear ${label}`} onClick={onClear}>
            ✕
          </IconButton>
        ) : null}
      </span>
      {hint ? (
        <span className="font-mono text-[0.6rem] text-ink-mute">{hint}</span>
      ) : null}
    </div>
  );
}

export const ACCENT_SWATCH_PRESETS = [
  { name: "digigraph", hex: "#e5b765" }, // canon-allow: pins canon --accent-digigraph hex (packages/design/tokens.css)
  { name: "digiquant", hex: "#3dd6c4" }, // canon-allow: pins canon --accent-digiquant hex (packages/design/tokens.css)
  { name: "digisearch", hex: "#5aa3c4" }, // canon-allow: pins canon --accent-digisearch hex (packages/design/tokens.css)
  { name: "digichat", hex: "#e2708a" }, // canon-allow: pins canon --accent-digichat hex (packages/design/tokens.css)
  { name: "digikey", hex: "#d97a5a" }, // canon-allow: pins canon --accent-digikey hex (packages/design/tokens.css)
  { name: "digismith", hex: "#6fa3a3" }, // canon-allow: pins canon --accent-digismith hex (packages/design/tokens.css)
  { name: "digiclaw", hex: "#b87840" }, // canon-allow: pins canon --accent-digiclaw hex (packages/design/tokens.css)
  { name: "digibase", hex: "#9ea0a5" }, // canon-allow: pins canon --accent-digibase hex (packages/design/tokens.css)
  { name: "digistore", hex: "#7b7fc7" }, // canon-allow: pins canon --accent-digistore hex (packages/design/tokens.css)
  { name: "digivault", hex: "#9d8fc9" }, // canon-allow: pins canon --accent-digivault hex (packages/design/tokens.css)
] as const;

/**
 * Preset + custom swatch picker for an accent hex. Uses the TriRow
 * span-label + aria-labelledby group pattern (NOT Field: Field
 * clone-injects id/aria into its direct child, and the swatch grid is a
 * group of buttons rather than a single control). Every pick commits
 * through `onCommit` under the same `#rrggbb` gate the text rows used; a
 * refused commit leaves the `value` prop unchanged, so the highlight
 * (`aria-pressed` on the committed value) reverts on its own.
 */
export function SwatchRow({
  label,
  value,
  hint,
  onCommit,
  onClear,
}: {
  label: string;
  value: string | undefined;
  hint?: string;
  /** Returns whether the commit applied; the highlight reverts on false. */
  onCommit: (v: string) => boolean;
  onClear?: () => void;
}) {
  const labelId = useId();
  const hintId = useId();
  const current = (value ?? "").toLowerCase();
  const colorValue =
    value !== undefined && /^#[0-9a-fA-F]{6}$/.test(value) ? value : "#000000";
  const tryCommit = (hex: string) => {
    if (!/^#[0-9a-fA-F]{6}$/.test(hex)) return false;
    return onCommit(hex.toLowerCase());
  };
  return (
    <div className="grid min-w-0 gap-[0.35rem]">
      <span id={labelId} className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">
        {label}
      </span>
      <div
        role="group"
        aria-labelledby={labelId}
        aria-describedby={hint ? hintId : undefined}
        className="grid min-w-0 gap-1"
      >
        <div className="devkit-swatches">
          {ACCENT_SWATCH_PRESETS.map((preset) => (
            <button
              key={preset.name}
              type="button"
              className="devkit-swatch"
              aria-pressed={current === preset.hex}
              aria-label={preset.name}
              title={`${preset.name} ${preset.hex}`}
              style={{ backgroundColor: preset.hex }}
              onClick={() => {
                tryCommit(preset.hex);
              }}
            />
          ))}
        </div>
        <span className="flex items-center gap-1">
          <span className="font-mono text-[0.6rem] text-ink-mute">Custom…</span>
          <input
            type="color"
            aria-label={`Custom ${label}`}
            value={colorValue}
            onChange={(e) => {
              tryCommit(e.target.value);
            }}
          />
          <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">
            {value ?? "not set"}
          </span>
          {onClear && value ? (
            <IconButton title={`Clear ${label}`} aria-label={`Clear ${label}`} onClick={onClear}>
              ✕
            </IconButton>
          ) : null}
        </span>
      </div>
      {hint ? (
        <span id={hintId} className="font-mono text-[0.6rem] text-ink-mute">{hint}</span>
      ) : null}
    </div>
  );
}

/**
 * Live WCAG contrast readout for the accent pair. The below-minimum
 * warning is dismissible; the dismissal is keyed to the current pair so
 * any value change re-arms it. Dismissal never blocks the commit itself.
 */
export function AccentContrastReadout({
  color,
  foreground,
}: {
  color: string | undefined;
  foreground: string | undefined;
}) {
  const [dismissedPair, setDismissedPair] = useState<string | null>(null);
  if (color === undefined || foreground === undefined) return null;
  if (!/^#[0-9a-fA-F]{6}$/.test(color) || !/^#[0-9a-fA-F]{6}$/.test(foreground)) {
    return null;
  }
  const ratio = contrast(color, foreground);
  const text = `Contrast ${ratio.toFixed(2)}:1`;
  if (ratio >= CONTRAST_MINIMUM) {
    return <p className="font-mono text-[0.6rem] text-ink-mute">{text}</p>;
  }
  const pair = `${color.toLowerCase()} on ${foreground.toLowerCase()}`;
  if (dismissedPair === pair) {
    return <p className="font-mono text-[0.6rem] text-ink-mute">{text}</p>;
  }
  return (
    <p className="font-mono text-[0.6rem] text-ink-mute">
      {text} is below the 4.5:1 (WCAG AA) minimum — text on this accent may be
      hard to read.{" "}
      <button type="button" onClick={() => setDismissedPair(pair)}>
        Dismiss
      </button>
    </p>
  );
}

type McpServer = NonNullable<NonNullable<DigichatDeployment["mcp"]>["servers"]>[number];
type ToolEntry = NonNullable<NonNullable<DigichatDeployment["tools"]>["catalog"]>[number];

const BACKEND_TYPES = [
  "digigraph",
  "foundry",
  "openai-completions",
  "openai-responses",
  "anthropic",
  "google-vertex",
  "langgraph",
  "ag-ui",
  "a2a",
] as const;

/** Editable scalar fields per backend variant (apiKeyEnv names an env var). */
const BACKEND_FIELDS: Record<string, Array<{ key: string; label: string }>> = {
  digigraph: [
    { key: "digisearchIndex", label: "digisearch index" },
    { key: "vaultPathPrefix", label: "vault path prefix" },
  ],
  foundry: [
    { key: "projectEndpoint", label: "project endpoint (https)" },
    { key: "agentName", label: "agent name" },
  ],
  "openai-completions": [
    { key: "baseUrl", label: "base URL (https)" },
    { key: "model", label: "model" },
    { key: "apiKeyEnv", label: "API key env var (DIGICHAT_BACKEND_*)" },
  ],
  "openai-responses": [
    { key: "baseUrl", label: "base URL (https)" },
    { key: "model", label: "model" },
    { key: "apiKeyEnv", label: "API key env var (DIGICHAT_BACKEND_*)" },
  ],
  anthropic: [
    { key: "model", label: "model" },
    { key: "apiKeyEnv", label: "API key env var (DIGICHAT_BACKEND_*)" },
  ],
  "google-vertex": [
    { key: "project", label: "GCP project" },
    { key: "location", label: "location" },
    { key: "model", label: "model" },
  ],
  langgraph: [
    { key: "apiUrl", label: "API URL (https)" },
    { key: "assistantId", label: "assistant id" },
    { key: "apiKeyEnv", label: "API key env var (optional)" },
  ],
  "ag-ui": [
    { key: "url", label: "URL (https)" },
    { key: "apiKeyEnv", label: "API key env var (optional)" },
  ],
  a2a: [
    { key: "baseUrl", label: "base URL (https)" },
    { key: "apiKeyEnv", label: "API key env var (optional)" },
  ],
};

/**
 * Step-4 accordion editors: every section rewrites the draft text through
 * the tested `draft.ts` helpers, so forms and raw YAML can never diverge.
 * Values are read from the draft's last-valid `parsed` deployment; secrets
 * stay masked (sentinel-aware) and restore from disk on save.
 */
export function DevkitEditors({
  draft,
  commit,
  scrollRoot,
}: {
  draft: EntryDraft;
  commit: EditorsCommit;
  /** Sidebar scroll container: the scroll-spy observer root (fallback null). */
  scrollRoot?: React.RefObject<HTMLElement | null>;
}) {
  const scope = draft.scope;
  const dep = draft.parsed;
  const chrome = dep?.chrome;
  const features = dep?.features;

  const scalar = (path: string[], v: string) =>
    commit(setScalar(draft.text, scope, path, v));
  const clearing = (path: string[], v: string) =>
    commit(v === "" ? deleteKey(draft.text, scope, path) : setScalar(draft.text, scope, path, v));
  const clearingItem = (listPath: string[], i: number, field: string, v: string) =>
    commit(
      v === ""
        ? deleteListItemField(draft.text, scope, listPath, i, field)
        : setListItemScalar(draft.text, scope, listPath, i, field, v),
    );
  const tri = (path: string[]) => (v: boolean | undefined) =>
    commit(
      v === undefined
        ? deleteKey(draft.text, scope, path)
        : setBoolean(draft.text, scope, path, v),
    );

  // Backend variant shown: local state so the type switch renders its fields
  // immediately, before the debounced validation round-trips.
  const [backendType, setBackendType] = useState<string>(dep?.backend.type ?? "digigraph");
  // Raw-YAML edits bypass the switch: resync when the draft's own type moves
  // underneath the local state (m6 — no more wrong-variant fields).
  // Deferred via queueMicrotask (repo pattern for set-state-in-effect).
  useEffect(() => {
    const t = dep?.backend.type;
    if (!t) return;
    queueMicrotask(() => {
      setBackendType((prev) => (prev === t ? prev : t));
    });
  }, [dep?.backend.type]);
  const backendOfType =
    dep?.backend && dep.backend.type === backendType ? dep.backend : null;
  const backendFieldValue = (key: string): string | undefined => {
    if (!backendOfType || !("type" in backendOfType)) return undefined;
    const v: unknown = (backendOfType as Record<string, unknown>)[key];
    return typeof v === "string" ? v : undefined;
  };
  const switchBackend = (next: string): boolean => {
    if (next === backendType) return true;
    if (
      !window.confirm(
        `Switch backend to ${next}? Backend-specific fields will be discarded.`,
      )
    ) {
      return false;
    }
    const applied = commit(
      applyAll(draft.text, [
        (t) => deleteKey(t, scope, ["backend"]),
        (t) => setScalar(t, scope, ["backend", "type"], next),
      ]),
    );
    // Only move the local variant when the text edit landed — otherwise the
    // fields would show a variant the draft doesn't have.
    if (applied) setBackendType(next);
    return applied;
  };

  // Welcome body is a string|string[] union: single-line commits as scalar,
  // multi-line as a block list; a scalar↔list shape change needs delete+set.
  const bodyPath = ["chrome", "welcome", "body"];
  const commitBody = (lines: string[]): boolean => {
    if (lines.length === 0) {
      return commit(deleteKey(draft.text, scope, bodyPath));
    }
    const op =
      lines.length === 1
        ? (t: string) => setScalar(t, scope, bodyPath, lines[0])
        : (t: string) => setStringList(t, scope, bodyPath, lines);
    let edit = op(draft.text);
    if (!edit.applied) {
      edit = applyAll(draft.text, [(t) => deleteKey(t, scope, bodyPath), op]);
    }
    return commit(edit);
  };
  const bodyLines = (() => {
    const b = chrome?.welcome?.body;
    if (b === undefined) return [];
    return typeof b === "string" ? [b] : [...b];
  })();

  const [newTool, setNewTool] = useState({ id: "", label: "", def: false });
  const [newServer, setNewServer] = useState({ id: "", url: "", label: "" });
  const tools = dep?.tools?.catalog ?? [];
  const servers = dep?.mcp?.servers ?? [];

  const languageGroups: SelectOptionGroup[] = (() => {
    const current = chrome?.defaultLanguage;
    const featured: string[] = [...FEATURED_LANGUAGE_CODES];
    if (current && !featured.includes(current)) {
      return [
        { label: "featured", options: featured },
        { label: "current", options: [current] },
      ];
    }
    return [{ label: "featured", options: featured }];
  })();

  // Group shell (spec §1–§2): single-open disclosure over the three
  // groups, sticky scroll-spy nav, one observer that opens but never closes.
  const [openGroup, setOpenGroup] = useState<string | null>("basics");
  const anchorsRef = useRef(new Map<string, HTMLElement>());
  const latestTopsRef = useRef(new Map<string, number>());
  // Manual toggle is the only path that may close: remember which group was
  // closed so observer refires electing that same group do not reopen it.
  // Released when a different group becomes visible or a nav click opens one.
  const manualClosedRef = useRef<string | null>(null);
  // Nav-click settle hold: after scrollToGroup arms this, observer votes for
  // any OTHER group are stale mid-scroll geometry (the clicked anchor settles
  // below root-top under max-scroll clamp, so the election keeps favoring an
  // earlier group) and must not yank the clicked group away. Released on
  // arrival (vote elects the target), user scroll takeover, manual toggle, or
  // a settle timeout backstop.
  const navTargetRef = useRef<string | null>(null);
  const navTimerRef = useRef<number | null>(null);
  const disarmNavTarget = () => {
    navTargetRef.current = null;
    if (navTimerRef.current !== null) {
      window.clearTimeout(navTimerRef.current);
      navTimerRef.current = null;
    }
  };
  const openGroupRef = useRef<string | null>(openGroup);
  useEffect(() => {
    openGroupRef.current = openGroup;
  }, [openGroup]);

  useEffect(() => {
    const targets = GROUPS.map((g) => anchorsRef.current.get(g.id)).filter(
      (el): el is HTMLElement => el != null,
    );
    if (targets.length === 0 || typeof IntersectionObserver === "undefined") return;
    const rootEl = scrollRoot?.current ?? null;
    const rootTop = () => rootEl?.getBoundingClientRect().top ?? 0;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          latestTopsRef.current.set(
            (entry.target as HTMLElement).id,
            entry.boundingClientRect.top - rootTop(),
          );
        }
        const visible = visibleGroupFromEntries(
          GROUPS.map((g) => ({
            id: g.id,
            top: latestTopsRef.current.get(g.id) ?? Number.POSITIVE_INFINITY,
          })),
        );
        // Arrival releases the nav-click hold (timer no longer needed); the
        // vote below then applies with the hold cleared.
        if (navTargetRef.current !== null && visible === navTargetRef.current) {
          disarmNavTarget();
        }
        const next = applyScrollSpyVote(
          openGroupRef.current,
          manualClosedRef.current,
          visible,
          navTargetRef.current,
        );
        manualClosedRef.current = next.manualClosed;
        setOpenGroup(next.open);
      },
      {
        root: rootEl,
        rootMargin: "-20% 0px -65% 0px",
        threshold: 0,
      },
    );
    targets.forEach((t) => observer.observe(t));
    // User scroll takeover ends a nav-click settle: wheel/touch input means
    // the user grabbed the scroll, so votes apply normally again at once
    // instead of waiting for the settle timeout.
    const disarmOnUserScroll = () => {
      if (navTargetRef.current !== null) disarmNavTarget();
    };
    rootEl?.addEventListener("wheel", disarmOnUserScroll, { passive: true });
    rootEl?.addEventListener("touchmove", disarmOnUserScroll, { passive: true });
    return () => {
      observer.disconnect();
      rootEl?.removeEventListener("wheel", disarmOnUserScroll);
      rootEl?.removeEventListener("touchmove", disarmOnUserScroll);
      disarmNavTarget();
    };
  }, [scrollRoot]);

  const setGroupFromTrigger = (groupId: string, isOpen: boolean) => {
    disarmNavTarget(); // manual toggle takes over from any nav-click settle
    if (isOpen) {
      manualClosedRef.current = null;
      setOpenGroup(groupId);
    } else {
      manualClosedRef.current = groupId;
      setOpenGroup(null);
    }
  };

  const scrollToGroup = (id: string) => {
    manualClosedRef.current = null;
    disarmNavTarget();
    navTargetRef.current = id;
    setOpenGroup(id);
    const reduce =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    anchorsRef.current
      .get(id)
      ?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    // Settle backstop: if the clicked anchor can never become foremost (short
    // content clamps the scroll with the anchor still below root-top), no
    // arrival vote ever fires — release the hold so later user scrolls apply
    // normally. No vote can fire after geometry goes static, so the timeout
    // itself never changes which group is open.
    navTimerRef.current = window.setTimeout(disarmNavTarget, 1200);
  };

  const sectionBody = (title: SectionTitle): React.ReactNode => {
    switch (title) {
      case "Identity":
        return (
          <>
        {draft.entryId === null ? (
          <TextRow
            label="slug (lowercase letters, digits, hyphens)"
            value={dep?.slug ?? "new-deployment"}
            required
            onCommit={(v) => {
              if (!isValidSlug(v)) return false; // revert: row restores display
              return scalar(["slug"], v);
            }}
          />
        ) : (
          <div className="flex items-start justify-between gap-2 py-0.5 text-xs">
            <dt className="shrink-0 text-muted-foreground">slug</dt>
            <dd className="min-w-0 text-right font-mono break-words">{dep?.slug}</dd>
          </div>
        )}
        <TextRow
          label="aliases (comma separated)"
          value={(dep?.aliases ?? []).join(", ")}
          placeholder="old-slug, partner-slug"
          onCommit={(v) =>
            commit(
              setStringList(
                draft.text,
                scope,
                ["aliases"],
                v
                  .split(",")
                  .map((s) => s.trim())
                  .filter((s) => s !== ""),
              ),
            )
          }
        />
          </>
        );
      case "Backend":
        return (
          <>
        <SelectRow
          label="backend type"
          value={backendType}
          options={BACKEND_TYPES}
          hint="Switching discards backend-specific fields (with confirmation)."
          onCommit={switchBackend}
        />
        {(BACKEND_FIELDS[backendType] ?? []).map(({ key, label }) => (
          <TextRow
            key={key}
            label={label}
            value={backendFieldValue(key)}
            onCommit={(v) => clearing(["backend", key], v)}
            onClear={() => commit(deleteKey(draft.text, scope, ["backend", key]))}
          />
        ))}
        <SegRow
          label="persistence"
          value={dep?.persistence ?? "none"}
          options={["none", "memory", "server"]}
          onCommit={(v) => scalar(["persistence"], v)}
        />
        <SegRow
          label="auth"
          value={dep?.auth ?? "anonymous"}
          options={["anonymous", "session"]}
          onCommit={(v) => scalar(["auth"], v)}
        />
          </>
        );
      case "Appearance":
        return (
          <>
        <SelectRow
          label="skin"
          value={chrome?.skin ?? "digichat"}
          groups={[{ label: "skins", options: THREAD_SKINS }]}
          onCommit={(v) => scalar(["chrome", "skin"], v)}
        />
        <SegRow
          label="theme"
          value={chrome?.theme ?? "light"}
          options={["dark", "light"]}
          onCommit={(v) => scalar(["chrome", "theme"], v)}
        />
        <SelectRow
          label="mode"
          value={chrome?.mode ?? "embed"}
          options={["app", "embed", "modal", "sidebar"]}
          onCommit={(v) => scalar(["chrome", "mode"], v)}
        />
        <TextRow
          label="title"
          value={chrome?.title}
          onCommit={(v) => clearing(["chrome", "title"], v)}
          onClear={() => commit(deleteKey(draft.text, scope, ["chrome", "title"]))}
        />
        <TextRow
          label="welcome title"
          value={chrome?.welcome?.title}
          onCommit={(v) => scalar(["chrome", "welcome", "title"], v)}
          onClear={() => commit(deleteKey(draft.text, scope, ["chrome", "welcome"]))}
          hint="Clearing removes the whole welcome copy (title is required)."
        />
        <TextListRow label="welcome body (one per line)" values={bodyLines} onCommit={commitBody} />
        <TextRow
          label="composer placeholder"
          value={chrome?.placeholder}
          onCommit={(v) => clearing(["chrome", "placeholder"], v)}
          onClear={() => commit(deleteKey(draft.text, scope, ["chrome", "placeholder"]))}
        />
        <TextListRow
          label="starter suggestions (one per line)"
          values={chrome?.suggestions ?? []}
          onCommit={(lines) => commit(setStringList(draft.text, scope, ["chrome", "suggestions"], lines))}
        />
        <div className="grid min-w-0 grid-cols-2 gap-2">
          <SwatchRow
            label="accent color"
            value={chrome?.accent?.color}
            onCommit={(v) => {
              if (!/^#[0-9a-fA-F]{6}$/.test(v)) return false; // revert on invalid hex
              return scalar(["chrome", "accent", "color"], v);
            }}
            onClear={() => commit(deleteKey(draft.text, scope, ["chrome", "accent"]))}
            hint="Hex only (#rrggbb); clearing removes the accent override."
          />
          <SwatchRow
            label="accent foreground"
            value={chrome?.accent?.foreground}
            onCommit={(v) => {
              if (!/^#[0-9a-fA-F]{6}$/.test(v)) return false;
              return scalar(["chrome", "accent", "foreground"], v);
            }}
          />
        </div>
        <AccentContrastReadout
          color={chrome?.accent?.color}
          foreground={chrome?.accent?.foreground}
        />
        <TriRow
          label="attribution credit"
          value={chrome?.attribution}
          hint="Inherit (unset) shows the credit."
          onCommit={tri(["chrome", "attribution"])}
        />
        <SegRow
          label="launcher mode"
          value={chrome?.launcher?.mode ?? "inherit"}
          options={["inherit", "dot", "bar"]}
          onCommit={(v) =>
            commit(
              v === "inherit"
                ? deleteKey(draft.text, scope, ["chrome", "launcher", "mode"])
                : setScalar(draft.text, scope, ["chrome", "launcher", "mode"], v),
            )
          }
        />
        <TextRow
          label="launcher hotkey"
          value={chrome?.launcher?.hotkey}
          onCommit={(v) => clearing(["chrome", "launcher", "hotkey"], v)}
          onClear={() => commit(deleteKey(draft.text, scope, ["chrome", "launcher", "hotkey"]))}
        />
        <TextRow
          label="launcher label"
          value={chrome?.launcher?.label}
          onCommit={(v) => clearing(["chrome", "launcher", "label"], v)}
          onClear={() => commit(deleteKey(draft.text, scope, ["chrome", "launcher", "label"]))}
        />
        <SelectRow
          label="reply language default"
          value={chrome?.defaultLanguage ?? "en"}
          groups={languageGroups}
          onCommit={(v) => scalar(["chrome", "defaultLanguage"], v)}
        />
        <SegRow
          label="user bubble alignment"
          value={chrome?.transcript?.userAlign ?? "right"}
          options={["right", "left"]}
          onCommit={(v) => scalar(["chrome", "transcript", "userAlign"], v)}
        />
          </>
        );
      case "Features":
        return (
          <>
        <BoolRow label="attachments" checked={features?.attachments ?? true} onCommit={(v) => commit(setBoolean(draft.text, scope, ["features", "attachments"], v))} />
        <BoolRow label="dictation" checked={features?.dictation ?? false} onCommit={(v) => commit(setBoolean(draft.text, scope, ["features", "dictation"], v))} />
        <BoolRow label="speech" checked={features?.speech ?? false} onCommit={(v) => commit(setBoolean(draft.text, scope, ["features", "speech"], v))} />
        <BoolRow label="sources" checked={features?.sources ?? true} onCommit={(v) => commit(setBoolean(draft.text, scope, ["features", "sources"], v))} />
        <BoolRow
          label="model picker (legacy alias of models.allowPicker)"
          checked={features?.modelPicker ?? false}
          onCommit={(v) => commit(setBoolean(draft.text, scope, ["features", "modelPicker"], v))}
        />
        <BoolRow label="branch picker" checked={features?.branchPicker ?? true} onCommit={(v) => commit(setBoolean(draft.text, scope, ["features", "branchPicker"], v))} />
        <SelectRow
          label="chain-of-thought view"
          value={features?.view ?? "balanced"}
          options={["hidden", "compact", "balanced", "detailed"]}
          onCommit={(v) => scalar(["features", "view"], v)}
        />
        <SegRow
          label="reasoning override"
          value={features?.thinking ?? "auto"}
          options={["auto", "collapsed", "open"]}
          onCommit={(v) => scalar(["features", "thinking"], v)}
        />
        <SegRow
          label="page context"
          value={features?.pageContext ?? "visible"}
          options={["off", "silent", "visible"]}
          onCommit={(v) => scalar(["features", "pageContext"], v)}
        />
          </>
        );
      case "Models":
        return (
          <>
        <TextRow
          label="default model"
          value={dep?.models.default}
          placeholder=" unset — no default"
          onCommit={(v) => clearing(["models", "default"], v)}
          onClear={() => commit(deleteKey(draft.text, scope, ["models", "default"]))}
        />
        <TextListRow
          label="available models (one per line)"
          values={dep?.models.available ?? []}
          onCommit={(lines) => commit(setStringList(draft.text, scope, ["models", "available"], lines))}
        />
        <TriRow label="model picker" value={dep?.models.allowPicker} onCommit={tri(["models", "allowPicker"])} />
          </>
        );
      case "Tools":
        return (
          <>
        <BoolRow
          label="allow user toggle"
          checked={dep?.tools?.allowUserToggle ?? true}
          onCommit={(v) => commit(setBoolean(draft.text, scope, ["tools", "allowUserToggle"], v))}
        />
        {tools.map((t: ToolEntry, i: number) => (
          <Card key={`${t.id}-${i}`} dress="chat">
            <CardHeader>
              <CardTitle className="min-w-0 truncate">{t.id}</CardTitle>
              <CardAction>
                <IconButton
                  title={`Remove ${t.id}`}
                  aria-label={`Remove ${t.id}`}
                  onClick={() => commit(removeListItem(draft.text, scope, ["tools", "catalog"], i))}
                >
                  ✕
                </IconButton>
              </CardAction>
            </CardHeader>
            <CardContent className="flex flex-col gap-1">
              <TextRow
                label="id"
                value={t.id}
                required
                onCommit={(v) => commit(setListItemScalar(draft.text, scope, ["tools", "catalog"], i, "id", v))}
              />
              <TextRow
                label="label"
                value={t.label}
                onCommit={(v) => clearingItem(["tools", "catalog"], i, "label", v)}
                onClear={() => commit(deleteListItemField(draft.text, scope, ["tools", "catalog"], i, "label"))}
              />
              <BoolRow
                label="default on"
                checked={t.default ?? false}
                onCommit={(v) => commit(setListItemScalar(draft.text, scope, ["tools", "catalog"], i, "default", v))}
              />
            </CardContent>
          </Card>
        ))}
        <div className="flex flex-col gap-1 rounded border border-dashed p-1.5">
          <span className="text-[11px] text-muted-foreground">Add tool</span>
          <Input
            dress="chat"
            value={newTool.id}
            placeholder="id"
            aria-label="New tool id"
            spellCheck={false}
            onChange={(e) => setNewTool((s) => ({ ...s, id: e.target.value }))}
          />
          <Input
            dress="chat"
            value={newTool.label}
            placeholder="label (optional)"
            aria-label="New tool label"
            spellCheck={false}
            onChange={(e) => setNewTool((s) => ({ ...s, label: e.target.value }))}
          />
          <span className="flex items-center gap-2">
            <Switch
              checked={newTool.def}
              onCheckedChange={(v) => setNewTool((s) => ({ ...s, def: v }))}
              aria-label="New tool default on"
            />
            <span className="text-xs">default on</span>
            <Button
              type="button"
              dress="chat"
              disabled={newTool.id.trim() === ""}
              onClick={() => {
                const item: Record<string, string | boolean> = { id: newTool.id.trim() };
                if (newTool.label.trim() !== "") item.label = newTool.label.trim();
                if (newTool.def) item.default = true;
                if (commit(appendListItem(draft.text, scope, ["tools", "catalog"], item))) {
                  setNewTool({ id: "", label: "", def: false });
                }
              }}
              className="ml-auto"
            >
              Add
            </Button>
          </span>
        </div>
          </>
        );
      case "MCP servers":
        return (
          <>
        <BoolRow
          label="allow user servers"
          checked={dep?.mcp?.allowUserServers ?? false}
          onCommit={(v) => commit(setBoolean(draft.text, scope, ["mcp", "allowUserServers"], v))}
        />
        <BoolRow
          label="show add-server form"
          checked={dep?.mcp?.allowAddForm ?? false}
          hint="Ignored unless user servers are allowed."
          onCommit={(v) => commit(setBoolean(draft.text, scope, ["mcp", "allowAddForm"], v))}
        />
        {servers.map((s: McpServer, i: number) => (
          <Card key={`${s.id}-${i}`} dress="chat">
            <CardHeader>
              <CardTitle className="min-w-0 truncate">{s.id}</CardTitle>
              <CardAction>
                <IconButton
                  title={`Remove ${s.id}`}
                  aria-label={`Remove ${s.id}`}
                  onClick={() => commit(removeListItem(draft.text, scope, ["mcp", "servers"], i))}
                >
                  ✕
                </IconButton>
              </CardAction>
            </CardHeader>
            <CardContent className="flex flex-col gap-1">
              <TextRow
                label="id (lowercase slug)"
                value={s.id}
                required
                onCommit={(v) => commit(setListItemScalar(draft.text, scope, ["mcp", "servers"], i, "id", v))}
              />
              <TextRow
                label="URL (BFF-only, never projected)"
                value={s.url}
                required
                onCommit={(v) => commit(setListItemScalar(draft.text, scope, ["mcp", "servers"], i, "url", v))}
              />
              <TextRow
                label="label"
                value={s.label}
                onCommit={(v) => clearingItem(["mcp", "servers"], i, "label", v)}
                onClear={() => commit(deleteListItemField(draft.text, scope, ["mcp", "servers"], i, "label"))}
              />
              <BoolRow
                label="default on"
                checked={s.default ?? false}
                onCommit={(v) => commit(setListItemScalar(draft.text, scope, ["mcp", "servers"], i, "default", v))}
              />
              <SecretRow
                label="token (operator secret)"
                state={secretStateInList(draft.text, scope, ["mcp", "servers"], i, "token")}
                hint="Prefer tokenEnv. Untouched rows restore from disk on save."
                onReplace={(v) => commit(setListItemScalar(draft.text, scope, ["mcp", "servers"], i, "token", v))}
                onClear={() => commit(deleteListItemField(draft.text, scope, ["mcp", "servers"], i, "token"))}
              />
              <TextRow
                label="token env var"
                value={s.tokenEnv}
                placeholder="MY_MCP_TOKEN"
                onCommit={(v) => clearingItem(["mcp", "servers"], i, "tokenEnv", v)}
                onClear={() => commit(deleteListItemField(draft.text, scope, ["mcp", "servers"], i, "tokenEnv"))}
              />
              <TextRow
                label="auth header (e.g. X-API-Key)"
                value={s.authHeader}
                onCommit={(v) => clearingItem(["mcp", "servers"], i, "authHeader", v)}
                onClear={() => commit(deleteListItemField(draft.text, scope, ["mcp", "servers"], i, "authHeader"))}
              />
            </CardContent>
          </Card>
        ))}
        <div className="flex flex-col gap-1 rounded border border-dashed p-1.5">
          <span className="text-[11px] text-muted-foreground">Add server</span>
          <Input
            dress="chat"
            value={newServer.id}
            placeholder="id (lowercase slug)"
            aria-label="New server id"
            spellCheck={false}
            onChange={(e) => setNewServer((s) => ({ ...s, id: e.target.value }))}
          />
          <Input
            dress="chat"
            value={newServer.url}
            placeholder="https://…/mcp"
            aria-label="New server URL"
            spellCheck={false}
            onChange={(e) => setNewServer((s) => ({ ...s, url: e.target.value }))}
          />
          <Input
            dress="chat"
            value={newServer.label}
            placeholder="label (optional)"
            aria-label="New server label"
            spellCheck={false}
            onChange={(e) => setNewServer((s) => ({ ...s, label: e.target.value }))}
          />
          <Button
            type="button"
            dress="chat"
            disabled={newServer.id.trim() === "" || newServer.url.trim() === ""}
            onClick={() => {
              const item: Record<string, string | boolean> = {
                id: newServer.id.trim(),
                url: newServer.url.trim(),
              };
              if (newServer.label.trim() !== "") item.label = newServer.label.trim();
              if (commit(appendListItem(draft.text, scope, ["mcp", "servers"], item))) {
                setNewServer({ id: "", url: "", label: "" });
              }
            }}
            className="ml-auto"
          >
            Add
          </Button>
        </div>
          </>
        );
      case "Gate":
        return (
          <>
        <SelectRow
          label="mode"
          value={dep?.gate.mode ?? "ungated"}
          options={["turn_limited", "ungated", "trial_form"]}
          onCommit={(v) => scalar(["gate", "mode"], v)}
        />
        <SelectRow
          label="activity detail"
          value={dep?.gate.activityDetail ?? "labels"}
          options={["off", "labels", "full"]}
          onCommit={(v) => scalar(["gate", "activityDetail"], v)}
        />
        <SelectRow
          label="LLM access"
          value={dep?.gate.llmAccess ?? "inherit"}
          options={["inherit", "free_then_byok", "byok_only", "backend_only", "operator"]}
          onCommit={(v) =>
            commit(
              v === "inherit"
                ? deleteKey(draft.text, scope, ["gate", "llmAccess"])
                : setScalar(draft.text, scope, ["gate", "llmAccess"], v),
            )
          }
        />
        <SecretRow
          label="quota consume URL (server-side)"
          state={secretState(draft.text, scope, ["gate", "consumeUrl"])}
          hint="Untouched rows restore from disk on save."
          onReplace={(v) => scalar(["gate", "consumeUrl"], v)}
          onClear={() => commit(deleteKey(draft.text, scope, ["gate", "consumeUrl"]))}
        />
        <TextRow
          label="locked contact"
          value={dep?.gate.lockedContact}
          onCommit={(v) => clearing(["gate", "lockedContact"], v)}
          onClear={() => commit(deleteKey(draft.text, scope, ["gate", "lockedContact"]))}
        />
        <TriRow label="show BYOK" value={dep?.gate.showByok} onCommit={tri(["gate", "showByok"])} />
        <TriRow
          label="show language selector"
          value={dep?.gate.showLanguageSelector}
          onCommit={tri(["gate", "showLanguageSelector"])}
        />
        <TriRow label="web search (legacy)" value={dep?.gate.webSearch} onCommit={tri(["gate", "webSearch"])} />
        <SelectRow
          label="minimum plan tier"
          value={dep?.gate.requiredPlanTier ?? "inherit"}
          options={["inherit", "desk", "studio", "enterprise"]}
          onCommit={(v) =>
            commit(
              v === "inherit"
                ? deleteKey(draft.text, scope, ["gate", "requiredPlanTier"])
                : setScalar(draft.text, scope, ["gate", "requiredPlanTier"], v),
            )
          }
        />
          </>
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <nav
        aria-label="Editor groups"
        className="sticky top-0 z-10 border-b border-hair bg-surface"
      >
        {GROUPS.map((group) => {
          const active = openGroup === group.id;
          return (
            <button
              key={group.id}
              type="button"
              onClick={() => scrollToGroup(group.id)}
              aria-current={active ? "true" : undefined}
              className={`devkit-navlink w-full border-l-2 px-2 py-1.5 text-left font-mono text-xs transition-colors motion-reduce:transition-none ${
                active
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-transparent text-ink-mute hover:text-ink"
              }`}
            >
              {group.label}
            </button>
          );
        })}
      </nav>
      {GROUPS.map((group) => (
        <section
          key={group.id}
          id={group.id}
          ref={(el) => {
            if (el) anchorsRef.current.set(group.id, el);
            else anchorsRef.current.delete(group.id);
          }}
          className="scroll-mt-28"
        >
          <Collapsible
            open={openGroup === group.id}
            onOpenChange={(isOpen) => setGroupFromTrigger(group.id, isOpen)}
            className="group rounded-lg border"
          >
            <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-2 py-1.5 font-mono text-xs font-semibold transition-colors hover:text-accent group-data-open:text-accent motion-reduce:transition-none">
              <span>{group.label}</span>
              <span
                aria-hidden="true"
                className="size-2 shrink-0 rotate-45 border-r-[1.6px] border-b-[1.6px] border-current transition-transform duration-300 group-data-open:-rotate-135 motion-reduce:transition-none"
              />
            </CollapsibleTrigger>
            <CollapsibleContent className="overflow-hidden transition-[height] duration-300 ease-out motion-reduce:transition-none data-open:h-[var(--collapsible-panel-height)] data-starting-style:h-0 data-ending-style:h-0 data-closed:h-0">
              <div className="flex flex-col gap-2 border-t p-2">
                {group.sections.map((title) => (
                  <div
                    key={title}
                    id={sectionAnchorId(title)}
                    className="flex scroll-mt-28 flex-col gap-2"
                  >
                    <h4 className="py-0.5 font-mono text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                      {title}
                    </h4>
                    {sectionBody(title)}
                  </div>
                ))}
              </div>
            </CollapsibleContent>
          </Collapsible>
        </section>
      ))}
    </div>
  );
}
