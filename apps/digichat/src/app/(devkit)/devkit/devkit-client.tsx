"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { p } from "@/lib/base-path";
import type { DigichatDeployment } from "@/lib/deploy-config/schema";
import { DevkitPreview } from "./devkit-preview";
import { DevkitSummary } from "./devkit-summary";
import { DevkitEditors, type EditorsCommit } from "./devkit-editors";
import { DevkitExportPane } from "./devkit-export-pane";
import {
  createDraft,
  createNewFileDraft,
  isDirty,
  withText,
  withValidation,
  type EntryDraft,
  type TextEdit,
} from "./draft";

/** Wire shape of GET /api/devkit/configs (mirrors DevkitEntry, JSON-safe). */
interface DevkitEntryWire {
  id: string;
  kind: "file" | "env";
  path: string;
  label: string;
  readOnly: boolean;
  ok: boolean;
  redactedText: string | null;
  issues: string[];
  deployment: DigichatDeployment | null;
}

const SIDEBAR_MIN = 240;
const SIDEBAR_MAX = 560;
const SIDEBAR_DEFAULT = 320;

const SIDEBAR_WIDTH_KEY = "devkit.sidebarWidth";

function loadSidebarWidth(): number {
  try {
    const raw = window.localStorage.getItem(SIDEBAR_WIDTH_KEY);
    const n = raw === null ? Number.NaN : Number.parseInt(raw, 10);
    if (Number.isFinite(n)) return Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, n));
  } catch {
    /* storage unavailable — fall through to default */
  }
  return SIDEBAR_DEFAULT;
}

function subscribeSidebarWidth(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

/**
 * Derive the draft scope from an entry id (`file:<rel>` → top-level
 * `deployment`, `file:<rel>#hosts/<key>` → that hosts sub-entry). Mirrors the
 * server's `parseDevkitSaveId`; env ids never reach here (view-only).
 */
function scopeForEntryId(id: string): string[] {
  const match = /^file:([^#]+?)(?:#hosts\/([^/]+))?$/.exec(id);
  if (match?.[2]) return ["hosts", match[2]];
  return ["deployment"];
}

/** Debounce for draft revalidation (plan contract: ~400ms). */
const VALIDATE_DEBOUNCE_MS = 400;

/**
 * Read the top-level `deployment.slug` out of draft text for the new-file
 * save id. Anchored to exactly-2-space indent so nested `slug:` keys (hosts
 * sub-entries carry their own) never match; the server re-verifies the
 * filename/text slug match fail-closed anyway.
 */
function slugFromDraftText(text: string): string | null {
  const match = /^  slug:\s*(\S+)\s*$/m.exec(text);
  if (!match) return null;
  // A quoted scalar (`slug: "demo"`) is valid YAML — strip one matching
  // quote layer so the save id never carries literal quote characters.
  const raw = match[1];
  if (
    raw.length >= 2 &&
    ((raw.startsWith('"') && raw.endsWith('"')) ||
      (raw.startsWith("'") && raw.endsWith("'")))
  ) {
    return raw.slice(1, -1);
  }
  return raw;
}

// Dev-only sidebar drag handle: the col-resize cursor is the drag affordance.
const RESIZE_HANDLE_CLASS =
  "w-1.5 shrink-0 cursor-col-resize border-r outline-none hover:bg-accent focus-visible:bg-accent"; // canon-allow: isolated devkit route without token bridge, no kit resize part, not product chrome

function useCopy(): [string | null, (text: string, which: string) => void] {
  const [copied, setCopied] = useState<string | null>(null);
  return [
    copied,
    (text, which) => {
      void navigator.clipboard
        ?.writeText(text)
        .then(() => {
          setCopied(which);
          window.setTimeout(() => setCopied((c) => (c === which ? null : c)), 1500);
        })
        .catch(() => setCopied(`failed:${which}`));
    },
  ];
}

/**
 * P1 devkit shell: categorized deployment picker, draft-driven live preview,
 * collapsible inspector sidebar, full-width chat. The sidebar edits a per-entry
 * draft (created from the served redacted text); the preview renders the
 * draft's last-valid `parsed` deployment. Form editors (Step 4), raw-YAML
 * editing + save UI (Step 5) plug into the same draft.
 */
export function DevkitClient() {
  const [entries, setEntries] = useState<DevkitEntryWire[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Synchronous mirror of the selection for stale-async guards (microtask /
  // debounce landings must not clobber a newer selection).
  const selectedIdRef = useRef<string | null>(null);
  const [draft, setDraft] = useState<EntryDraft | null>(null);
  // True while a "new deployment" draft owns the sidebar: the draft effect
  // must not clobber it with a selection-derived draft (there is none).
  const [isNewFile, setIsNewFile] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [editNotice, setEditNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);
  // Persisted width (external store, SSR-safe) + in-session drag override.
  const persistedWidth = useSyncExternalStore(
    subscribeSidebarWidth,
    loadSidebarWidth,
    () => SIDEBAR_DEFAULT,
  );
  const [dragWidth, setDragWidth] = useState<number | null>(null);
  const sidebarWidth = dragWidth ?? persistedWidth;
  const [copied, copy] = useCopy();

  useEffect(() => {
    if (dragWidth === null) return;
    try {
      window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(dragWidth));
    } catch {
      /* storage unavailable — width just won't persist */
    }
  }, [dragWidth]);

  const clampWidth = (n: number) => Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, Math.round(n)));

  const onResizeHandlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = sidebarWidth;
    const el = e.currentTarget;
    el.setPointerCapture(e.pointerId);
    const onMove = (ev: PointerEvent) => setDragWidth(clampWidth(startW + ev.clientX - startX));
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  useEffect(() => {
    let cancelled = false;
    fetch(p("/api/devkit/configs"))
      .then((res) => {
        if (!res.ok) throw new Error(`configs ${res.status}`);
        return res.json() as Promise<{ entries: DevkitEntryWire[] }>;
      })
      .then((data) => {
        if (cancelled) return;
        setEntries(data.entries);
        // Auto-select the first valid entry so the preview is never empty.
        const prev = selectedIdRef.current;
        const next =
          prev && data.entries.some((e) => e.id === prev)
            ? prev
            : (data.entries.find((e) => e.ok)?.id ?? data.entries[0]?.id ?? null);
        selectedIdRef.current = next;
        setSelectedId(next);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = entries?.find((e) => e.id === selectedId) ?? null;
  const files = entries?.filter((e) => e.kind === "file") ?? [];
  const envs = entries?.filter((e) => e.kind === "env") ?? [];

  // Cmd/Ctrl+/ toggles the inspector (mirrors chat-shell.tsx); never while
  // typing — inputs, textareas, and contentEditable keep the keystroke.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.key !== "/") return;
      const active = document.activeElement;
      if (
        active instanceof HTMLInputElement ||
        active instanceof HTMLTextAreaElement ||
        (active instanceof HTMLElement && active.isContentEditable)
      ) {
        return;
      }
      e.preventDefault();
      setCollapsed((v) => !v);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // (Re)create the draft whenever the selection resolves: file entries get a
  // draft seeded from their redacted text; env entries stay view-only.
  // Defer setState out of the synchronous effect body (repo pattern for
  // react-hooks/set-state-in-effect); a guard skips stale async landings.
  useEffect(() => {
    if (!entries) return;
    if (isNewFile) return; // the new-file draft owns the sidebar, not a selection
    const entry = entries.find((e) => e.id === selectedId) ?? null;
    const next =
      !entry || entry.kind !== "file" || entry.redactedText === null
        ? null
        : {
            ...createDraft({
              entryId: entry.id,
              scope: scopeForEntryId(entry.id),
              savedText: entry.redactedText,
              parsed: entry.deployment,
            }),
            // Seed saved-file issues so invalid files show problems before
            // the first debounced validation round-trips.
            issues: entry.issues,
          };
    const token = { selectedId };
    queueMicrotask(() => {
      if (token.selectedId !== selectedIdRef.current) return;
      setDraft(next);
    });
  }, [entries, selectedId, isNewFile]);

  // Revalidate the draft text, debounced; the fold keeps the last-valid
  // `parsed` while invalid, so the preview never drops. The effect keys on
  // text/scope only — folding a result spreads the same scope array through,
  // so validation never retriggers itself.
  const draftText = draft?.text;
  const draftScope = draft?.scope;
  const validateSeq = useRef(0);
  useEffect(() => {
    if (draftText === undefined || !draftScope) return;
    const text = draftText;
    const scope = draftScope;
    const id = ++validateSeq.current;
    const timer = window.setTimeout(() => {
      void fetch(p("/api/devkit/validate"), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text, scope }),
      })
        .then((res) => {
          if (!res.ok) throw new Error(`validate ${res.status}`);
          return res.json() as Promise<{
            issues: string[];
            deployment?: DigichatDeployment | null;
          }>;
        })
        .then((result) => {
          if (validateSeq.current !== id) return; // superseded
          setDraft((d) => (d && d.text === text ? withValidation(d, result) : d));
        })
        .catch(() => {
          // Network failure: keep the previous validation state.
        });
    }, VALIDATE_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [draftText, draftScope]);

  // Switching entries with a dirty draft needs an explicit nod — otherwise
  // the in-progress edit would silently vanish with the draft.
  const selectEntry = (id: string | null) => {
    if (id === selectedIdRef.current && !isNewFile) return;
    if (draft && isDirty(draft)) {
      if (!window.confirm("Discard unsaved draft changes?")) return;
    }
    selectedIdRef.current = id;
    setIsNewFile(false);
    setSelectedId(id);
    setSaveNotice(null);
  };

  // "New deployment": a blank draft with an editable slug (Identity section);
  // on save it becomes `config/<slug>.yaml` and joins the picker.
  const newDeployment = () => {
    if (draft && isDirty(draft)) {
      if (!window.confirm("Discard unsaved draft changes?")) return;
    }
    selectedIdRef.current = null;
    setIsNewFile(true);
    setSelectedId(null);
    setDraft(createNewFileDraft());
    setEditNotice(null);
    setSaveNotice(null);
  };

  // Persist the draft via the Step-2 save API, then refresh the entry list
  // and reselect — the draft effect rebuilds a clean draft from fresh text.
  const saveDraft = () => {
    if (!draft || saving) return;
    const id =
      draft.entryId ?? (() => {
        const slug = slugFromDraftText(draft.text);
        return slug ? `new:${slug}.yaml` : null;
      })();
    if (!id) {
      setSaveNotice("Cannot save: no deployment slug found in the draft.");
      return;
    }
    setSaving(true);
    setSaveNotice(null);
    const text = draft.text;
    void fetch(p("/api/devkit/save"), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id, text }),
    })
      .then((res) =>
        res.json().then(
          (data) => ({ status: res.status, data }) as {
            status: number;
            data: { ok: boolean; id?: string; issues?: string[] };
          },
        ),
      )
      .then(({ data }) => {
        if (!data.ok) {
          setSaveNotice((data.issues ?? ["Save failed."]).join("\n"));
          return;
        }
        // Refresh the list so the new/updated entry (and its .bak state)
        // appears, then reselect — the draft effect clears dirty from fresh
        // saved text.
        void fetch(p("/api/devkit/configs"))
          .then((res) => {
            if (!res.ok) throw new Error(`configs ${res.status}`);
            return res.json() as Promise<{ entries: DevkitEntryWire[] }>;
          })
          .then((fresh) => {
            setEntries(fresh.entries);
            const nextId = data.id ?? id;
            const resolved = fresh.entries.some((e) => e.id === nextId) ? nextId : null;
            selectedIdRef.current = resolved;
            setIsNewFile(false);
            setSelectedId(resolved);
          })
          .catch((err: unknown) => {
            setSaveNotice(err instanceof Error ? err.message : String(err));
          });
      })
      .catch((err: unknown) => {
        setSaveNotice(err instanceof Error ? err.message : String(err));
      })
      .finally(() => setSaving(false));
  };

  const previewDeployment = draft?.parsed ?? selected?.deployment ?? null;
  const previewDirty = draft ? isDirty(draft) : false;

  // Export source: the live draft when one exists, else the saved redacted text.
  const exportText = draft?.text ?? selected?.redactedText ?? null;
  const exportSlug =
    (exportText ? slugFromDraftText(exportText) : null) ?? selected?.label ?? "deployment";
  const exportHost =
    draft?.scope[0] === "hosts" && typeof draft.scope[1] === "string" ? draft.scope[1] : null;

  // Reloading/navigating away drops a dirty draft silently (entry-switch
  // and +new have confirm guards) — arm the native prompt while dirty (m8).
  useEffect(() => {
    if (!previewDirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [previewDirty]);

  // Step-4 form commits land here: applied edits rewrite the draft text
  // (debounced validation + preview follow); refusals surface a notice.
  // Commits are refused while a save is in flight — the post-save refresh
  // rebuilds the draft from disk and would silently drop them (m2).
  const commit: EditorsCommit = (edit: TextEdit) => {
    if (saving) {
      setEditNotice("Save in progress — edits resume when it lands.");
      return false;
    }
    if (!edit.applied) {
      setEditNotice("Edit not applied — unsupported structure here.");
      return false;
    }
    setEditNotice(null);
    setDraft((d) => (d ? withText(d, edit.text) : d));
    return true;
  };

  return (
    <main aria-label="digichat devkit" className="flex h-full min-h-0">
      {error ? (
        <p role="alert" className="p-4 text-sm text-destructive">
          Failed to load configs: {error}
        </p>
      ) : entries === null ? (
        <p className="p-4 text-sm text-muted-foreground">Loading configs…</p>
      ) : (
        <>
          <aside
            aria-label="Deployment inspector"
            style={{ width: collapsed ? 0 : sidebarWidth }}
            className="shrink-0 overflow-hidden transition-[width] duration-200"
          >
            <div
              style={{ width: sidebarWidth }}
              className="flex h-full flex-col gap-3 overflow-y-auto p-3"
            >
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold">digichat devkit</span>
                <button
                  type="button"
                  onClick={() => setCollapsed(true)}
                  aria-expanded={!collapsed}
                  aria-label="Hide inspector sidebar"
                  title="Hide inspector sidebar (⌘/)"
                  className="ml-auto rounded-md border px-2 py-1 text-xs text-muted-foreground hover:bg-accent"
                >
                  ⟨
                </button>
              </div>
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <label
                    htmlFor="devkit-deployment"
                    className="block text-[11px] font-semibold tracking-wide text-muted-foreground uppercase"
                  >
                    Deployments
                  </label>
                  <button
                    type="button"
                    onClick={newDeployment}
                    disabled={saving}
                    aria-label="New deployment"
                    title="Start a blank draft — saving writes config/<slug>.yaml"
                    className="rounded-md border px-2 py-0.5 text-xs text-muted-foreground hover:bg-accent"
                  >
                    + new
                  </button>
                </div>
                <select
                  id="devkit-deployment"
                  aria-label="Deployments"
                  value={selectedId ?? ""}
                  disabled={saving}
                  onChange={(e) => selectEntry(e.target.value || null)}
                  className="w-full rounded-md border bg-background px-2 py-1.5 font-mono text-xs"
                >
                  {selectedId === null ? <option value="">Select a deployment…</option> : null}
                  {files.length > 0 ? (
                    <optgroup label={`Local files (${files.length})`}>
                      {files.map((e) => (
                        <option key={e.id} value={e.id}>
                          {e.ok ? "●" : "○"} {e.label}
                          {e.ok ? "" : " (invalid)"}
                        </option>
                      ))}
                    </optgroup>
                  ) : null}
                  {envs.length > 0 ? (
                    <optgroup label={`Environment tenants (${envs.length})`}>
                      {envs.map((e) => (
                        <option key={e.id} value={e.id}>
                          {e.ok ? "●" : "○"} {e.label}
                          {e.ok ? "" : " (invalid)"}
                        </option>
                      ))}
                    </optgroup>
                  ) : null}
                </select>
              </div>

              {selected === null && !draft ? (
                <p className="text-xs text-muted-foreground">Select a deployment to inspect it.</p>
              ) : (
                <>
                  {selected?.readOnly ? (
                    <p className="rounded border px-1.5 py-1 text-[11px] text-muted-foreground">
                      read-only env tenant — never written
                    </p>
                  ) : null}
                  {isNewFile ? (
                    <p className="rounded border px-1.5 py-1 text-[11px] text-muted-foreground">
                      new deployment — set the slug in Identity, then save to
                      write config/&lt;slug&gt;.yaml
                    </p>
                  ) : null}
                  {(draft ? draft.issues : (selected?.issues ?? [])).length > 0 ? (
                    <ul className="rounded-lg border border-destructive/50 p-2 font-mono text-xs">
                      {(draft ? draft.issues : (selected?.issues ?? [])).map((issue) => (
                        <li key={issue} className="text-destructive">
                          {issue}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {editNotice ? (
                    <p role="status" className="rounded border px-1.5 py-1 text-[11px] text-muted-foreground">
                      {editNotice}
                    </p>
                  ) : null}
                  {saveNotice ? (
                    <p role="alert" className="rounded border border-destructive/50 px-1.5 py-1 font-mono text-[11px] whitespace-pre-wrap text-destructive">
                      {saveNotice}
                    </p>
                  ) : null}
                  {draft ? (
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={saveDraft}
                        disabled={saving || draft.issues.length > 0 || !isDirty(draft)}
                        aria-label="Save draft"
                        title={
                          draft.issues.length > 0
                            ? "Fix validation issues before saving"
                            : isDirty(draft)
                              ? "Write the draft to its YAML file"
                              : "No unsaved changes"
                        }
                        className="flex-1 rounded-md border px-2 py-1 text-xs hover:bg-accent disabled:opacity-50"
                      >
                        {saving ? "saving…" : "save"}
                      </button>
                      {isDirty(draft) ? (
                        <span aria-label="unsaved changes" title="Unsaved changes" className="text-xs text-muted-foreground">
                          ● unsaved
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">saved ✓</span>
                      )}
                    </div>
                  ) : null}
                  {draft ? (
                    <fieldset
                      disabled={saving}
                      className="m-0 min-w-0 border-0 p-0"
                      aria-label="Deployment editors"
                    >
                      <DevkitEditors
                        key={draft.entryId ?? "new"}
                        draft={draft}
                        commit={commit}
                      />
                    </fieldset>
                  ) : selected?.deployment ? (
                    <DevkitSummary deployment={selected.deployment} />
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      No file text for env tenants — configuration lives in the environment.
                    </p>
                  )}
                  {(draft || selected?.redactedText !== null) && (
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => setExportOpen(true)}
                        disabled={saving}
                        className="flex-1 rounded-md border px-2 py-1 text-xs hover:bg-accent disabled:opacity-50"
                      >
                        export ⧉
                      </button>
                      <button
                        type="button"
                        onClick={() => copy(draft ? draft.text : (selected?.redactedText ?? ""), "yaml")}
                        className="flex-1 rounded-md border px-2 py-1 text-xs hover:bg-accent"
                      >
                        {copied === "yaml" ? "copied ✓" : "copy YAML"}
                      </button>
                      {(draft?.parsed ?? selected?.deployment) ? (
                        <button
                          type="button"
                          onClick={() =>
                            copy(JSON.stringify(draft?.parsed ?? selected?.deployment, null, 2), "json")
                          }
                          className="flex-1 rounded-md border px-2 py-1 text-xs hover:bg-accent"
                        >
                          {copied === "json" ? "copied ✓" : "copy JSON"}
                        </button>
                      ) : null}
                    </div>
                  )}
                  {draft ? (
                    <details className="rounded-lg border">
                      <summary className="px-2 py-1.5 font-mono text-xs text-muted-foreground">
                        raw YAML{isDirty(draft) ? " ●" : ""}
                      </summary>
                      <textarea
                        aria-label="Raw YAML draft"
                        value={draft.text}
                        disabled={saving}
                        onChange={(e) =>
                          setDraft((d) => (d ? withText(d, e.target.value) : d))
                        }
                        spellCheck={false}
                        rows={20}
                        className="max-h-96 min-h-40 w-full resize-y overflow-auto border-t bg-muted/30 p-3 font-mono text-xs outline-none"
                      />
                    </details>
                  ) : selected?.redactedText !== null ? (
                    <details className="rounded-lg border">
                      <summary className="px-2 py-1.5 font-mono text-xs text-muted-foreground">
                        raw YAML
                      </summary>
                      <pre className="max-h-96 overflow-auto border-t bg-muted/30 p-3 font-mono text-xs">
                        {selected?.redactedText}
                      </pre>
                    </details>
                  ) : null}
                </>
              )}
            </div>
          </aside>
          {!collapsed ? (
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize inspector sidebar"
              aria-valuenow={sidebarWidth}
              aria-valuemin={SIDEBAR_MIN}
              aria-valuemax={SIDEBAR_MAX}
              tabIndex={0}
              onPointerDown={onResizeHandlePointerDown}
              onKeyDown={(e) => {
                if (e.key === "ArrowLeft") setDragWidth(clampWidth(sidebarWidth - 16));
                if (e.key === "ArrowRight") setDragWidth(clampWidth(sidebarWidth + 16));
              }}
              className={RESIZE_HANDLE_CLASS}
            />
          ) : (
            <div className="flex w-10 shrink-0 flex-col items-center border-r py-3">
              <button
                type="button"
                onClick={() => setCollapsed(false)}
                aria-expanded={false}
                aria-label="Show inspector sidebar"
                title="Show inspector sidebar (⌘/)"
                className="rounded-md border px-2 py-1 text-xs text-muted-foreground hover:bg-accent"
              >
                ⟩
              </button>
            </div>
          )}
          <section aria-label="Chat preview" className="min-w-0 flex-1 overflow-hidden">
            {previewDeployment ? (
              <DevkitPreview
                key={`${selected?.id ?? "new"}:${previewDeployment.chrome.skin}:${previewDeployment.chrome.theme}`}
                entryId={selected?.id ?? "new"}
                deployment={previewDeployment}
                dirty={previewDirty}
              />
            ) : (
              <p className="p-4 text-sm text-muted-foreground">
                {selected || draft ? "This entry has no valid deployment to preview." : "Loading…"}
              </p>
            )}
          </section>
          {exportOpen && exportText ? (
            <DevkitExportPane
              slug={exportSlug}
              host={exportHost}
              draftText={exportText}
              onClose={() => setExportOpen(false)}
            />
          ) : null}
        </>
      )}
    </main>
  );
}
