"use client";

import { useEffect, useState } from "react";
import { THREAD_SKINS } from "@digithings/ui/chat/skins";
import { Button, Field, Input, Switch, Textarea } from "@digithings/ui/ui";
import { FEATURED_LANGUAGE_CODES } from "@/lib/languages";
import type { DigichatDeployment } from "@/lib/deploy-config/schema";
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

const inputCls = "w-full rounded-md border bg-background px-2 py-1 font-mono text-xs";
const labelCls = "flex flex-col gap-1 text-xs";
const hintCls = "text-[11px] text-muted-foreground";

function Section({
  title,
  children,
  defaultOpen,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details className="rounded-lg border" open={defaultOpen}>
      <summary className="px-2 py-1.5 text-xs font-semibold">{title}</summary>
      <div className="flex flex-col gap-2 border-t p-2">{children}</div>
    </details>
  );
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
        <Button type="button" dress="chat" onClick={onClear} aria-label={`Clear ${label}`}>
          ✕
        </Button>
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

function SelectRow({
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
  return (
    <label className={labelCls}>
      <span className="text-muted-foreground">{label}</span>
      <select
        defaultValue={value}
        onChange={(e) => {
          if (!onCommit(e.target.value)) {
            e.target.value = value; // refused — revert, never diverge
          }
        }}
        className={inputCls}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
      {hint ? <span className={hintCls}>{hint}</span> : null}
    </label>
  );
}

/** Optional boolean: inherit (key absent) / on / off. */
function TriRow({
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
  return (
    <label className={labelCls}>
      <span className="text-muted-foreground">{label}</span>
      <select
        defaultValue={current}
        onChange={(e) => {
          const v = e.target.value;
          if (!onCommit(v === "inherit" ? undefined : v === "on")) {
            e.target.value = current; // refused — revert, never diverge
          }
        }}
        className={inputCls}
      >
        <option value="inherit">inherit (unset)</option>
        <option value="on">on</option>
        <option value="off">off</option>
      </select>
      {hint ? <span className={hintCls}>{hint}</span> : null}
    </label>
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
function SecretRow({
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
  return (
    <div className={labelCls}>
      <span className="text-muted-foreground">{label}</span>
      {replacing ? (
        <span className="flex gap-1">
          <input
            type="password"
            value={val}
            autoFocus
            placeholder="new secret value"
            onChange={(e) => setVal(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && val !== "") {
                if (!onReplace(val)) return; // refused — stay open, keep value
                setVal("");
                setReplacing(false);
              }
              if (e.key === "Escape") {
                setVal("");
                setReplacing(false);
              }
            }}
            className={`${inputCls} min-w-0 flex-1`}
          />
          <button
            type="button"
            disabled={val === ""}
            onClick={() => {
              if (!onReplace(val)) return; // refused — stay open, keep value
              setVal("");
              setReplacing(false);
            }}
            className="shrink-0 rounded-md border px-2 py-1 text-xs hover:bg-accent disabled:opacity-50"
          >
            Set
          </button>
          <button
            type="button"
            onClick={() => {
              setVal("");
              setReplacing(false);
            }}
            className="shrink-0 rounded-md border px-2 py-1 text-xs text-muted-foreground hover:bg-accent"
          >
            Cancel
          </button>
        </span>
      ) : (
        <span className="flex items-center gap-1">
          <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">
            {masked}
          </span>
          <button
            type="button"
            onClick={() => setReplacing(true)}
            className="shrink-0 rounded-md border px-2 py-1 text-xs hover:bg-accent"
          >
            {state === "absent" ? "Add" : "Replace"}
          </button>
          {onClear && state !== "absent" ? (
            <button
              type="button"
              title={`Clear ${label}`}
              aria-label={`Clear ${label}`}
              onClick={onClear}
              className="shrink-0 rounded-md border px-1.5 py-1 text-xs text-muted-foreground hover:bg-accent"
            >
              ✕
            </button>
          ) : null}
        </span>
      )}
      {hint ? <span className={hintCls}>{hint}</span> : null}
    </div>
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
}: {
  draft: EntryDraft;
  commit: EditorsCommit;
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

  const languageOptions = (() => {
    const current = chrome?.defaultLanguage;
    const base: string[] = [...FEATURED_LANGUAGE_CODES];
    if (current && !base.includes(current)) base.push(current);
    return base;
  })();

  return (
    <div className="flex flex-col gap-2">
      <Section title="Identity" defaultOpen>
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
      </Section>

      <Section title="Backend">
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
        <SelectRow
          label="persistence"
          value={dep?.persistence ?? "none"}
          options={["none", "memory", "server"]}
          onCommit={(v) => scalar(["persistence"], v)}
        />
        <SelectRow
          label="auth"
          value={dep?.auth ?? "anonymous"}
          options={["anonymous", "session"]}
          onCommit={(v) => scalar(["auth"], v)}
        />
      </Section>

      <Section title="Appearance">
        <SelectRow
          label="skin"
          value={chrome?.skin ?? "digichat"}
          options={THREAD_SKINS}
          onCommit={(v) => scalar(["chrome", "skin"], v)}
        />
        <div className={labelCls}>
          <span className="text-muted-foreground">theme</span>
          <span className="flex gap-1" role="group" aria-label="theme">
            {(["dark", "light"] as const).map((t) => (
              <button
                key={t}
                type="button"
                aria-pressed={(chrome?.theme ?? "light") === t}
                onClick={() => scalar(["chrome", "theme"], t)}
                className={`flex-1 rounded-md border px-2 py-1 font-mono text-xs hover:bg-accent ${
                  (chrome?.theme ?? "light") === t ? "bg-accent" : ""
                }`}
              >
                {t}
              </button>
            ))}
          </span>
        </div>
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
        <TextRow
          label="accent color"
          value={chrome?.accent?.color}
          placeholder="#rrggbb"
          onCommit={(v) => {
            if (!/^#[0-9a-fA-F]{6}$/.test(v)) return false; // revert on invalid hex
            return scalar(["chrome", "accent", "color"], v);
          }}
          onClear={() => commit(deleteKey(draft.text, scope, ["chrome", "accent"]))}
          hint="Hex only (#rrggbb); clearing removes the accent override."
        />
        <TextRow
          label="accent foreground"
          value={chrome?.accent?.foreground}
          placeholder="#rrggbb"
          onCommit={(v) => {
            if (!/^#[0-9a-fA-F]{6}$/.test(v)) return false;
            return scalar(["chrome", "accent", "foreground"], v);
          }}
        />
        <TriRow
          label="attribution credit"
          value={chrome?.attribution}
          hint="Inherit (unset) shows the credit."
          onCommit={tri(["chrome", "attribution"])}
        />
        <SelectRow
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
          options={languageOptions}
          onCommit={(v) => scalar(["chrome", "defaultLanguage"], v)}
        />
        <SelectRow
          label="user bubble alignment"
          value={chrome?.transcript?.userAlign ?? "right"}
          options={["right", "left"]}
          onCommit={(v) => scalar(["chrome", "transcript", "userAlign"], v)}
        />
      </Section>

      <Section title="Features">
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
        <SelectRow
          label="reasoning override"
          value={features?.thinking ?? "auto"}
          options={["auto", "collapsed", "open"]}
          onCommit={(v) => scalar(["features", "thinking"], v)}
        />
        <SelectRow
          label="page context"
          value={features?.pageContext ?? "visible"}
          options={["off", "silent", "visible"]}
          onCommit={(v) => scalar(["features", "pageContext"], v)}
        />
      </Section>

      <Section title="Models">
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
      </Section>

      <Section title="Tools">
        <BoolRow
          label="allow user toggle"
          checked={dep?.tools?.allowUserToggle ?? true}
          onCommit={(v) => commit(setBoolean(draft.text, scope, ["tools", "allowUserToggle"], v))}
        />
        {tools.map((t: ToolEntry, i: number) => (
          <div key={`${t.id}-${i}`} className="flex flex-col gap-1 rounded border p-1.5">
            <div className="flex items-center gap-1">
              <span className="min-w-0 flex-1 truncate font-mono text-xs">{t.id}</span>
              <button
                type="button"
                title={`Remove ${t.id}`}
                aria-label={`Remove ${t.id}`}
                onClick={() => commit(removeListItem(draft.text, scope, ["tools", "catalog"], i))}
                className="shrink-0 rounded-md border px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-accent"
              >
                ✕
              </button>
            </div>
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
          </div>
        ))}
        <div className="flex flex-col gap-1 rounded border border-dashed p-1.5">
          <span className="text-[11px] text-muted-foreground">Add tool</span>
          <input
            value={newTool.id}
            placeholder="id"
            spellCheck={false}
            onChange={(e) => setNewTool((s) => ({ ...s, id: e.target.value }))}
            className={inputCls}
          />
          <input
            value={newTool.label}
            placeholder="label (optional)"
            spellCheck={false}
            onChange={(e) => setNewTool((s) => ({ ...s, label: e.target.value }))}
            className={inputCls}
          />
          <span className="flex items-center gap-2">
            <label className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={newTool.def}
                onChange={(e) => setNewTool((s) => ({ ...s, def: e.target.checked }))}
                className="size-3.5 accent-current"
              />
              default on
            </label>
            <button
              type="button"
              disabled={newTool.id.trim() === ""}
              onClick={() => {
                const item: Record<string, string | boolean> = { id: newTool.id.trim() };
                if (newTool.label.trim() !== "") item.label = newTool.label.trim();
                if (newTool.def) item.default = true;
                if (commit(appendListItem(draft.text, scope, ["tools", "catalog"], item))) {
                  setNewTool({ id: "", label: "", def: false });
                }
              }}
              className="ml-auto rounded-md border px-2 py-1 text-xs hover:bg-accent disabled:opacity-50"
            >
              Add
            </button>
          </span>
        </div>
      </Section>

      <Section title="MCP servers">
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
          <div key={`${s.id}-${i}`} className="flex flex-col gap-1 rounded border p-1.5">
            <div className="flex items-center gap-1">
              <span className="min-w-0 flex-1 truncate font-mono text-xs">{s.id}</span>
              <button
                type="button"
                title={`Remove ${s.id}`}
                aria-label={`Remove ${s.id}`}
                onClick={() => commit(removeListItem(draft.text, scope, ["mcp", "servers"], i))}
                className="shrink-0 rounded-md border px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-accent"
              >
                ✕
              </button>
            </div>
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
          </div>
        ))}
        <div className="flex flex-col gap-1 rounded border border-dashed p-1.5">
          <span className="text-[11px] text-muted-foreground">Add server</span>
          <input
            value={newServer.id}
            placeholder="id (lowercase slug)"
            spellCheck={false}
            onChange={(e) => setNewServer((s) => ({ ...s, id: e.target.value }))}
            className={inputCls}
          />
          <input
            value={newServer.url}
            placeholder="https://…/mcp"
            spellCheck={false}
            onChange={(e) => setNewServer((s) => ({ ...s, url: e.target.value }))}
            className={inputCls}
          />
          <input
            value={newServer.label}
            placeholder="label (optional)"
            spellCheck={false}
            onChange={(e) => setNewServer((s) => ({ ...s, label: e.target.value }))}
            className={inputCls}
          />
          <button
            type="button"
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
            className="ml-auto rounded-md border px-2 py-1 text-xs hover:bg-accent disabled:opacity-50"
          >
            Add
          </button>
        </div>
      </Section>

      <Section title="Gate">
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
      </Section>
    </div>
  );
}
