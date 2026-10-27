"use client";

/**
 * Session menu docked above the composer (#3736 UI pass). Same chrome as the
 * slash palette: opaque, composer-width, command/label left, value right.
 * Arrow keys move; Enter toggles, opens a nested list, or commits an exclusive
 * pick (then the menu closes). Escape or Left goes back; Enter or Right
 * submits the row. The hovered or arrow-key row shows the same `>` chevron
 * as a user message and shifts its content right to make room for it.
 */

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { createPortal } from "react-dom";
import { DotMatrix } from "@digithings/ui/chat/dot-matrix";
import { Button, Input, Label } from "@digithings/ui/ui";
import { nextPaletteIndex, optionDraft, paneDraftForId, submenuRows, VIEW_LABELS } from "@digithings/digichat-ui";
import { useEmbedChatPrefs } from "@digithings/ui/chat/stock";
import {
  applyWellKnownMcp,
  wellKnownMcpGrouped,
  wellKnownMcpHost,
  wellKnownMcpSuggestions,
} from "@/components/stock/embed-mcp-catalog";
import {
  connectedMcpConfigs,
  connectedToolIsOn,
  connectedTools,
  cycleMcpAuth,
  emptyMcpConfig,
  MCP_AUTH,
  MCP_ID_RE,
  mcpConfigJson,
  mcpMenuSummaryFromConfigs,
  mcpStatus,
  mcpStatusLabel,
  parseMcpSeed,
  serverRowLabel,
  toolsMenuSummary,
  type SessionMcpConfig,
} from "@/components/stock/embed-mcp-flow";
import {
  applyThemePick,
  buildProductSlashCommands,
  currentThemeState,
  languageSelectOptions,
} from "@/lib/product-slash-commands";
import { languageDisplayName } from "@/lib/languages";
import {
  byokRequiresModel,
  validateBYOKKey,
  validateBYOKModel,
  type BYOKProvider,
} from "@/hooks/use-byok-key";
import { byokActivationGate, pingByokKey } from "@/lib/byok-ping";
import { HOUSE_BACKEND_ID } from "@/lib/provider-label";
import {
  CUSTOM_PROVIDER_MODEL,
  PROVIDER_MENU_ORDER,
  defaultProviderPick,
  providerDisplayName,
  providerKeyPlaceholder,
  providerModelChoices,
  sessionPickerModels,
  tryResolveProviderInput,
  wantsProviderKeyPing,
} from "@/components/stock/embed-provider-flow";
import { listenMcpOAuthResult, startMcpOAuth } from "@/components/stock/embed-mcp-oauth";
import { THINKING_MODES, VIEW_MODES } from "@/lib/view-modes";
import { TRACE_DENSITIES, TRACE_DENSITY_LABELS } from "@digithings/ui/chat/trace-spacing";
import { matchThemeStep, themeCycle } from "@digithings/ui/theme";

export type ComposerMenuKind =
  | "settings"
  | "models"
  | "mcp"
  | "tools"
  | "language"
  | "effort"
  | "search-engine"
  | "view"
  | "density"
  | "theme"
  | "thinking"
  | "provider"
  | "help";

type MenuView =
  | "main"
  | "language"
  | "models"
  | "effort"
  | "search-engine"
  | "view"
  | "density"
  | "theme"
  | "thinking"
  | "tools"
  | "mcp"
  | "mcp-edit"
  | "provider"
  | "provider-key"
  | "provider-model"
  | "help";

export type MenuRow = {
  id: string;
  label: string;
  value: string;
  /** Accessible name override (defaults to `label`); used to expose full ids. */
  ariaLabel?: string;
  activate: () => void;
  checked?: boolean;
  /** Single-choice list: radio disc, not On/Off. */
  exclusive?: boolean;
  /** Provider label. Not a control, so arrows and Home/End skip it. */
  heading?: boolean;
  /** Composer text while this row is selected (`/language English`). */
  insert?: string;
  /** Option text the pane filter matches (`English`, `default dark`). */
  token?: string;
  aliases?: readonly string[];
  /**
   * /tools tree: a tool row under its service. `mid` draws `├─`, `last` draws
   * `└─`, like a file listing under its folder.
   */
  branch?: "mid" | "last";
  /** Collapsible provider header: whether its children are shown. */
  expanded?: boolean;
  /**
   * /models path tree: the rails of the enclosing folders (`│  ` or three
   * spaces each), drawn before the branch glyph of a nested row.
   */
  treePrefix?: string;
};

/**
 * A tool's name as `/tools` shows it: a trailing note in parentheses, such as
 * "(help docs)", is dropped, so the page lists tool names only.
 */
export function bareToolLabel(label: string): string {
  // String scan, not a regex: a backtracking pattern here is a ReDoS (CodeQL js/polynomial-redos).
  const trimmed = label.trim();
  if (!trimmed.endsWith(")")) return trimmed;
  const open = trimmed.lastIndexOf("(");
  if (open < 0 || trimmed.slice(open + 1, -1).includes(")")) return trimmed;
  const bare = trimmed.slice(0, open).trim();
  return bare || trimmed;
}

/** One node of the /models path tree: a folder (an id segment) or a leaf (a model id). */
export type ModelPathNode =
  | { kind: "folder"; name: string; path: string; children: ModelPathNode[] }
  | { kind: "leaf"; name: string; id: string };

/**
 * The /models tree. Each raw model id is split on `/` like a file path:
 * every segment but the last is a folder, the last is the leaf label. Deeper
 * ids nest deeper; an id without a slash is a top-level leaf, with no
 * invented folder. At every level folders come first, then leaves, each
 * sorted alphabetically (like the /tools list: folders, then files).
 */
export function buildModelPathTree(ids: readonly string[]): ModelPathNode[] {
  const root: ModelPathNode[] = [];
  const seen = new Set<string>();
  for (const id of ids) {
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const parts = id.split("/").filter((part) => part.length > 0);
    if (!parts.length) continue;
    let level = root;
    let path = "";
    for (const part of parts.slice(0, -1)) {
      path = path ? `${path}/${part}` : part;
      let folder = level.find(
        (node): node is Extract<ModelPathNode, { kind: "folder" }> =>
          node.kind === "folder" && node.path === path,
      );
      if (!folder) {
        folder = { kind: "folder", name: part, path, children: [] };
        level.push(folder);
      }
      level = folder.children;
    }
    level.push({ kind: "leaf", name: parts[parts.length - 1]!, id });
  }
  const sort = (nodes: ModelPathNode[]): ModelPathNode[] => {
    nodes.sort((a, b) =>
      a.kind !== b.kind ? (a.kind === "folder" ? -1 : 1) : a.name.localeCompare(b.name),
    );
    for (const node of nodes) if (node.kind === "folder") sort(node.children);
    return nodes;
  };
  return sort(root);
}

/** Folder paths that hold an id (`a/b/c` -> `a`, `a/b`). */
export function modelFolderAncestors(id: string): string[] {
  const parts = id.split("/").filter((part) => part.length > 0);
  const out: string[] = [];
  for (let i = 1; i < parts.length; i++) out.push(parts.slice(0, i).join("/"));
  return out;
}

/** The /tools tree branch glyph for a row under a service. */
export function treeBranchGlyph(branch: MenuRow["branch"]): string {
  if (branch === "last") return "└─";
  if (branch === "mid") return "├─";
  return "";
}

export type ComposerModelPicker = {
  presets: readonly { id: string; label: string; model: string }[];
  groups: readonly {
    /** Backend provider id: the model id prefix before the first "/". */
    provider: string;
    models: readonly { id: string; label: string; premium?: boolean }[];
    /** A hand-written group can still be manual-only. The catalog never sets it. */
    premium?: boolean;
  }[];
  showFullList: boolean;
};

/**
 * The cursor is the row Enter commits, so a page that has a current value
 * opens on it. The index is read from the rows the page renders, so the list
 * a page shows and the list it indexes are the same list by construction and
 * no separate order constant can drift out of step with the rendering.
 *
 * A page without a current value (the root, the on/off toggles, the tool and
 * server lists) has no row to land on and starts at the top.
 */
export function cursorOnCurrentRow(rows: readonly MenuRow[]): number {
  const index = rows.findIndex(
    (row) => row.exclusive === true && row.checked === true && row.heading !== true,
  );
  if (index >= 0) return index;
  const first = rows.findIndex((row) => row.heading !== true);
  return first >= 0 ? first : 0;
}

function selectableIndexes(rows: readonly MenuRow[]): number[] {
  const indexes: number[] = [];
  rows.forEach((row, index) => {
    if (row.heading !== true) indexes.push(index);
  });
  return indexes;
}

function stepSelectable(current: number, delta: number, rows: readonly MenuRow[]): number {
  const selectable = selectableIndexes(rows);
  if (!selectable.length) return 0;
  const pos = selectable.indexOf(current);
  if (pos < 0) {
    // On a heading (or past the end): one step lands on the nearest selectable
    // row in that direction, without applying the delta a second time.
    if (delta > 0) return selectable.find((index) => index > current) ?? selectable[0] ?? 0;
    return [...selectable].reverse().find((index) => index < current) ?? selectable[selectable.length - 1] ?? 0;
  }
  return selectable[nextPaletteIndex(pos, delta, selectable.length)] ?? selectable[0] ?? 0;
}

export const stepSelectableForTests = stepSelectable;

/**
 * The menu is a tree, not a set of modes: every page has exactly one parent.
 * Back is `MENU_PARENT[view]`; only the root closes. Adding a page means adding
 * one entry here, and it inherits Esc / ← behaviour.
 */
const MENU_PARENT: Record<MenuView, MenuView | null> = {
  main: null,
  language: "main",
  models: "main",
  effort: "main",
  "search-engine": "main",
  view: "main",
  density: "main",
  theme: "main",
  thinking: "main",
  tools: "main",
  mcp: "main",
  "mcp-edit": "mcp",
  provider: "main",
  "provider-key": "provider",
  "provider-model": "provider",
  help: "main",
};

/** Escape from a pane writes the command without the trailing space. */
const PANE_BACK_TOKEN: Partial<Record<MenuView, string>> = {
  language: "/language",
  models: "/models",
  effort: "/effort",
  "search-engine": "/search-engine",
  view: "/view",
  density: "/density",
  theme: "/theme",
  thinking: "/thinking",
  tools: "/tools",
  mcp: "/mcp",
  provider: "/provider",
  help: "/help",
};

const EFFORTS = ["low", "medium", "high"] as const;

const SEARCH_ENGINES = [
  "auto",
  "internal",
  "exa",
  "tavily",
  "parallel",
  "firecrawl",
  "tinyfish",
] as const;

const SEARCH_ENGINE_LABELS: Record<string, string> = {
  auto: "Auto · in-house",
  internal: "In-house",
  exa: "Exa",
  tavily: "Tavily",
  parallel: "Parallel",
  firecrawl: "Firecrawl",
  tinyfish: "Tinyfish",
};

const THINKING_LABELS: Record<string, string> = {
  auto: "Auto · follow view",
  collapsed: "Collapsed",
  open: "Open",
};

// digichat-local composer menu rows (not the kit DropdownMenu). These carry
// their own pointer cursor because the kit owns no equivalent row.
const MCP_SUGGEST_ROW_CLASS =
  "hover:bg-surface-2/50 flex w-full cursor-pointer items-baseline justify-between gap-4 rounded-none px-3 py-1.5 text-start text-sm outline-none outline-offset-[-1px]"; // canon-allow: digichat-local composer menu; kit owns no equivalent

const MENU_ROW_CLASS =
  "flex w-full cursor-pointer items-center gap-2 px-2 py-1 text-start text-sm outline-none"; // canon-allow: digichat-local composer menu; kit owns no equivalent

function slashName(id: string): string {
  return id.startsWith("/") ? id : `/${id}`;
}

function initialView(kind: ComposerMenuKind): MenuView {
  if (kind === "models") return "models";
  if (kind === "language") return "language";
  if (kind === "effort") return "effort";
  if (kind === "search-engine") return "search-engine";
  if (kind === "view") return "view";
  if (kind === "density") return "density";
  if (kind === "theme") return "theme";
  if (kind === "thinking") return "thinking";
  if (kind === "tools") return "tools";
  if (kind === "mcp") return "mcp";
  if (kind === "provider") return "provider";
  if (kind === "help") return "help";
  return "main";
}

function composerHost(): HTMLElement | null {
  if (typeof document === "undefined") return null;
  return document.querySelector<HTMLElement>('[data-thread-skin="digichat"] .aui-composer-root');
}

/**
 * Square scroll indicator for the menu body.
 *
 * Safari draws its overlay scrollbar as an OS capsule and ignores
 * `::-webkit-scrollbar` shape rules, so the native bar is hidden and this
 * 6px track/thumb is painted instead. It follows scroll position, keyboard
 * scrolling and list changes, and can be dragged.
 */
function MenuScrollbar({ targetRef }: { targetRef: React.RefObject<HTMLDivElement | null> }) {
  const [thumb, setThumb] = useState<{ top: number; height: number } | null>(null);

  useEffect(() => {
    const el = targetRef.current;
    if (!el) return;
    const update = () => {
      const { scrollTop, scrollHeight, clientHeight } = el;
      if (scrollHeight <= clientHeight + 1) {
        setThumb(null);
        return;
      }
      const height = Math.max(12, Math.round((clientHeight / scrollHeight) * clientHeight));
      const maxTop = clientHeight - height;
      const maxScroll = scrollHeight - clientHeight;
      setThumb({
        top: maxScroll > 0 ? Math.round((scrollTop / maxScroll) * maxTop) : 0,
        height,
      });
    };
    update();
    el.addEventListener("scroll", update, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      observer?.disconnect();
    };
  }, [targetRef]);

  if (!thumb) return null;

  const startDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const el = targetRef.current;
    if (!el) return;
    event.preventDefault();
    const startY = event.clientY;
    const startScroll = el.scrollTop;
    const maxScroll = el.scrollHeight - el.clientHeight;
    const track = el.clientHeight - thumb.height;
    const move = (e: PointerEvent) => {
      if (track <= 0) return;
      el.scrollTop = startScroll + ((e.clientY - startY) / track) * maxScroll;
    };
    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end, { once: true });
  };

  return (
    <div className="dc-composer-menu-scroll" aria-hidden>
      <div
        className="dc-composer-menu-thumb"
        style={{ top: thumb.top, height: thumb.height }}
        onPointerDown={startDrag}
      />
    </div>
  );
}

export function EmbedComposerMenu({
  kind,
  models,
  defaultModel,
  picker,
  onClose,
  onActivateProvider,
  onClearProvider,
  onPickSessionModel,
  providerActive,
  initialProvider,
  providerSeed,
  mcpSeed,
}: {
  kind: ComposerMenuKind;
  models?: readonly string[];
  /** Deployment default: `auto` (or empty) makes Auto the checked first row. */
  defaultModel?: string;
  /** Catalog presets and provider groups. Absent keeps the id list. */
  picker?: ComposerModelPicker;
  onClose: () => void;
  onActivateProvider?: (key: string, provider: BYOKProvider, model: string) => void;
  onClearProvider?: () => void;
  onPickSessionModel?: (id: string) => void;
  providerActive?: { provider: BYOKProvider; model: string } | null;
  initialProvider?: BYOKProvider;
  providerSeed?: string;
  mcpSeed?: string;
}) {
  const api = useEmbedChatPrefs();
  const menuBodyRef = useRef<HTMLDivElement | null>(null);
  const available = sessionPickerModels(models ?? [], providerActive?.provider ?? null);
  const languages = useMemo(() => languageSelectOptions(), []);
  const toolOnInput = useMemo(
    () => ({
      digisearch: api.prefs.digisearch,
      vault: api.prefs.vault,
      webSearch: api.prefs.webSearch,
      extraToolOn: api.extraToolOn,
    }),
    [api],
  );
  const toolRows = useMemo(
    () =>
      connectedTools({
        hasDigisearch: api.hasDigisearch,
        hasVault: api.hasVault,
        tenantAllowsWeb: api.tenantAllowsWeb,
        catalogTools: api.catalogTools,
        mcpServers: api.mcpServers,
        mcpCustom: api.prefs.mcpCustom,
      }),
    [api],
  );
  const mcpConfigs = useMemo(
    () => connectedMcpConfigs(api.mcpServers, api.prefs.mcpCustom),
    [api.mcpServers, api.prefs.mcpCustom],
  );

  const [view, setView] = useState<MenuView>(() => initialView(kind));
  const [cursor, setCursor] = useState(0);
  /** The page the cursor was last seeded for; a page change seeds it again. */
  const [seededView, setSeededView] = useState<MenuView | null>(null);
  const [providerPick, setProviderPick] = useState<BYOKProvider>(
    () =>
      tryResolveProviderInput(providerSeed ?? "") ??
      defaultProviderPick(providerActive?.provider, initialProvider),
  );
  const [keyDraft, setKeyDraft] = useState("");
  const [modelDraft, setModelDraft] = useState("");
  const [customModel, setCustomModel] = useState(false);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [providerPending, setProviderPending] = useState(false);
  const [liveModels, setLiveModels] = useState<{ id: string; label: string }[] | undefined>();
  const [mcpDraft, setMcpDraft] = useState<SessionMcpConfig>(() => emptyMcpConfig());
  const [mcpFieldName, setMcpFieldName] = useState("");
  const [mcpFieldValue, setMcpFieldValue] = useState("");
  const [mcpError, setMcpError] = useState<string | null>(null);
  const [mcpOAuthBusy, setMcpOAuthBusy] = useState(false);
  const [mcpSuggestIndex, setMcpSuggestIndex] = useState(-1);
  const [mcpIdDropdownOpen, setMcpIdDropdownOpen] = useState(false);
  // The suggestion list overlays the menu, so it is portalled out of the menu
  // body's scroll box. This box is the anchor the list follows.
  const [mcpIdAnchor, setMcpIdAnchor] = useState<{
    top: number;
    left: number;
    width: number;
  } | null>(null);
  const mcpIdFieldRef = useRef<HTMLDivElement | null>(null);
  const keyInputRef = useRef<HTMLInputElement>(null);
  const customModelRef = useRef<HTMLInputElement>(null);
  const aliveRef = useRef(true);
  const echoArmed = useRef(false);
  const mcpDraftRef = useRef(mcpDraft);
  const keyFormId = useId();
  const openKey = `${kind}\0${providerSeed ?? ""}\0${mcpSeed ?? ""}`;
  const [appliedOpen, setAppliedOpen] = useState("");
  /** Provider headers the visitor opened or closed; null means the default. */
  const [expandedProviders, setExpandedProviders] = useState<Record<string, boolean | undefined> | null>(null);

  useEffect(() => {
    mcpDraftRef.current = mcpDraft;
  }, [mcpDraft]);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  if (appliedOpen !== openKey) {
    setAppliedOpen(openKey);
    const next = initialView(kind);
    const providerSeeded =
      kind === "provider" ? tryResolveProviderInput(providerSeed ?? "") : undefined;
    const mcpOpened = kind === "mcp" ? parseMcpSeed(mcpSeed ?? "") : undefined;
    if (providerSeeded) {
      setView("provider-key");
      setProviderPick(providerSeeded);
    } else if (mcpOpened === "new") {
      setMcpDraft(emptyMcpConfig());
      setView("mcp-edit");
    } else if (typeof mcpOpened === "string") {
      const hit =
        connectedMcpConfigs(api.mcpServers, api.prefs.mcpCustom).find((s) => s.id === mcpOpened) ??
        applyWellKnownMcp({ ...emptyMcpConfig(), label: mcpOpened }, mcpOpened);
      setMcpDraft(hit);
      setView("mcp-edit");
    } else {
      setView(next);
      if (kind === "provider") {
        setProviderPick(defaultProviderPick(providerActive?.provider, initialProvider));
      }
    }
    setKeyDraft("");
    setModelDraft("");
    setCustomModel(false);
    setProviderError(null);
    setLiveModels(undefined);
    setMcpFieldName("");
    setMcpFieldValue("");
    setMcpError(null);
    setMcpSuggestIndex(-1);
    setMcpIdDropdownOpen(false);
    setExpandedProviders(null);
  }

  const commitExclusive = useCallback(
    (apply: () => void) => {
      apply();
      if (api.composerDraftBound) queueMicrotask(() => api.setComposerDraft?.(""));
      else onClose();
    },
    [api, onClose],
  );

  /**
   * The root is the same command list the `/` palette filters — one source of
   * truth, so going back never lands on a second, shorter "main". Rows that
   * name a page open it in place; actions run and close the menu.
   */
  const mainRows = useMemo((): MenuRow[] => {
    const NODE_BY_ID: Partial<Record<string, MenuView>> = {
      models: "models",
      mcp: "mcp",
      tools: "tools",
      language: "language",
      view: "view",
      density: "density",
      theme: "theme",
      thinking: "thinking",
      effort: "effort",
      "search-engine": "search-engine",
      byok: "provider",
      help: "help",
    };
    return [
      ...buildProductSlashCommands(api)
        .filter((command) => command.id !== "settings")
        .map((command) => {
          const node = NODE_BY_ID[command.id];
          const draft = node ? paneDraftForId(command.id) : null;
          return {
            id: command.id,
            label: command.label ?? `/${command.id}`,
            value: command.description ?? "",
            ...(draft ? { insert: draft } : {}),
            activate: node
              ? () => {
                  if (api.composerDraftBound && draft) api.setComposerDraft?.(draft);
                  else setView(node);
                }
              : () => {
                  command.execute();
                  if (api.composerDraftBound) api.setComposerDraft?.("");
                  onClose();
                },
          };
        }),
      // A two-state setting, so it is one row that flips rather than a page of
      // options. The label names the state you would switch to, the value
      // names the one you are in.
      {
        id: "scroll",
        label: slashName(api.prefs.scroll === "free" ? "scroll follow" : "scroll free"),
        value: api.prefs.scroll === "free" ? "Free" : "Follow",
        checked: api.prefs.scroll === "follow",
        activate: () => {
          commitExclusive(() =>
            api.setScroll(api.prefs.scroll === "free" ? "follow" : "free"),
          );
        },
      },
    ];
  }, [api, onClose]);

  const languageRows = useMemo(
    (): MenuRow[] =>
      languages.map((o) => {
        const selected = api.prefs.language === o.value;
        const native = o.native !== o.label ? o.native : "";
        return {
          id: o.value,
          label: `${o.value}  ${o.label}`,
          value: native,
          checked: selected,
          exclusive: true,
          insert: optionDraft("/language", o.label),
          token: o.label,
          ...(native ? { aliases: [native] } : {}),
          activate: () => {
            commitExclusive(() => api.setLanguage(o.value));
          },
        };
      }),
    [languages, api, commitExclusive],
  );

  const modelRows = useMemo((): MenuRow[] => {
    // A connected BYOK provider replaces the house catalog with that
    // provider's own models. The catalog picker is the house list.
    if (picker && !providerActive) {
      const selected = api.prefs.model;
      const autoPreset = picker.presets.find((preset) => preset.id === "auto");
      const selectedPreset = picker.presets.find((preset) => `preset:${preset.id}` === selected);
      // The row to open by default: the selected model, or the Auto default.
      const currentModel =
        selectedPreset?.model ??
        (selected && selected !== "auto" && !selected.startsWith("preset:")
          ? selected
          : undefined) ??
        autoPreset?.model ??
        (defaultModel?.includes("/") ? defaultModel : "");
      // Default: the folders holding the current model are open.
      const defaultOpen: Record<string, boolean> = {};
      for (const path of currentModel ? modelFolderAncestors(currentModel) : []) {
        defaultOpen[path] = true;
      }
      const opened = expandedProviders ?? defaultOpen;
      const toggleProvider = (path: string) => {
        setExpandedProviders((prev) => {
          const base = prev ?? defaultOpen;
          const currentlyOpen = filtering
            ? base[path] !== false
            : base[path] === true;
          // During filtering the default is open, so closing stores `false`
          // and re-opening clears back to the (open) default.
          const next = currentlyOpen
            ? false
            : filtering
              ? undefined
              : true;
          return { ...base, [path]: next };
        });
      };
      const presetRows: MenuRow[] = picker.presets.map((preset) => {
        const token = `preset:${preset.id}`;
        const checked =
          preset.id === "auto"
            ? !selected || selected === "auto" || selected === token
            : selected === token;
        return {
          id: token,
          label: preset.label,
          value: "",
          checked,
          exclusive: true,
          insert: optionDraft("/models", preset.label),
          token: preset.label,
          aliases: [preset.id],
          activate: () => {
            const next = preset.id === "auto" ? "" : token;
            commitExclusive(() => {
              api.setModel(next);
              onPickSessionModel?.(next);
            });
          },
        };
      });
      // Provider groups as a /tools-style tree: a /provider row whose children
      // are the raw model ids. Activating the header collapses or expands it.
      const filtering = Boolean(api.paletteQuery?.trim());
      const leafRow = (
        node: Extract<ModelPathNode, { kind: "leaf" }>,
        branch: MenuRow["branch"],
        treePrefix: string,
      ): MenuRow => ({
        id: node.id,
        // The row reads the last path segment. The selected value, the API
        // id and the toolbar name stay the full id. The accessible name keeps
        // the full raw id so assistive tech keeps the provider association.
        ariaLabel: node.id,
        label: node.name,
        value: "",
        checked: selected === node.id,
        exclusive: true,
        branch,
        treePrefix,
        insert: optionDraft("/models", node.id),
        token: node.id,
        // `gpt` finds `openai/gpt-6-luna`: the filter matches prefixes.
        aliases: node.name !== node.id ? [node.name] : [],
        activate: () => {
          commitExclusive(() => {
            api.setModel(node.id);
            onPickSessionModel?.(node.id);
          });
        },
      });
      const treeRows = (nodes: ModelPathNode[], depth: number, rails: string): MenuRow[] =>
        nodes.flatMap((node, index): MenuRow[] => {
          const last = index === nodes.length - 1;
          // Top level has no glyph (like a /tools service or a bare id).
          const branch: MenuRow["branch"] = depth === 0 ? undefined : last ? "last" : "mid";
          const prefix = depth === 0 ? "" : rails;
          if (node.kind === "leaf") return [leafRow(node, filtering ? undefined : branch, prefix)];
          // A typed filter searches every folder at every depth.
          // Filtering force-opens every folder by default, but a manual toggle
          // still wins, so the header is not a visible no-op while filtering.
          const open = filtering
            ? opened[node.path] !== false
            : opened[node.path] === true;
          const header: MenuRow = {
            id: `folder:${node.path}`,
            label: `/${node.name}`,
            value: "",
            expanded: open,
            branch,
            treePrefix: prefix,
            token: node.path,
            activate: () => {
              toggleProvider(node.path);
            },
          };
          if (!open) return [header];
          const childRails = depth === 0 ? "" : `${rails}${last ? "   " : "│  "}`;
          return [header, ...treeRows(node.children, depth + 1, childRails)];
        });
      const groupRows: MenuRow[] = picker.showFullList
        ? treeRows(
            buildModelPathTree(picker.groups.flatMap((group) => group.models.map((m) => m.id))),
            0,
            "",
          )
        : [];
      if (presetRows.length || groupRows.length) return [...presetRows, ...groupRows];
    }
    // Auto is only a real option when the deployment default is Auto (no
    // pinned model); a tenant that pins a default should not offer a way to
    // silently leave it.
    const defaultIsAuto =
      !providerActive &&
      defaultModel !== undefined &&
      (!defaultModel.trim() || defaultModel.trim() === "auto");
    const autoRows: MenuRow[] = defaultIsAuto
      ? [
          {
            id: "auto",
            label: "auto",
            value: "deployment default",
            checked: !api.prefs.model || api.prefs.model === "auto",
            exclusive: true,
            insert: optionDraft("/models", "auto"),
            token: "auto",
            activate: () => {
              commitExclusive(() => api.setModel(""));
            },
          },
        ]
      : [];
    if (!available.length) {
      if (autoRows.length) return autoRows;
      return [
        {
          id: "none",
          label: "No published models",
          value: "",
          activate: () => {
            setView("main");
          },
        },
      ];
    }
    return [
      ...autoRows,
      ...available.map((id) => ({
        id,
        label: id,
        value: "",
        checked: (providerActive?.model || api.prefs.model) === id,
        exclusive: true,
        insert: optionDraft("/models", id),
        token: id,
        activate: () => {
          commitExclusive(() => {
            api.setModel(id);
            onPickSessionModel?.(id);
          });
        },
      })),
    ];
  }, [
    available,
    api,
    commitExclusive,
    defaultModel,
    expandedProviders,
    onPickSessionModel,
    picker,
    providerActive,
  ]);

  const effortRows = useMemo(
    (): MenuRow[] =>
      EFFORTS.map((id) => ({
        id,
        label: slashName(`effort ${id}`),
        value: "",
        checked: api.prefs.effort === id,
        exclusive: true,
        insert: optionDraft("/effort", id),
        token: id,
        activate: () => {
          commitExclusive(() => api.setEffort(id));
        },
      })),
    [api, commitExclusive],
  );

  const engineRows = useMemo(
    (): MenuRow[] =>
      SEARCH_ENGINES.map((id) => ({
        id,
        label: slashName(`search-engine ${id}`),
        value: SEARCH_ENGINE_LABELS[id] ?? "",
        checked: (api.prefs.searchEngine || "auto") === id,
        exclusive: true,
        insert: optionDraft("/search-engine", id),
        token: id,
        activate: () => {
          commitExclusive(() => api.setSearchEngine(id));
        },
      })),
    [api, commitExclusive],
  );

  const viewRows = useMemo(
    (): MenuRow[] =>
      VIEW_MODES.map((id) => ({
        id,
        label: slashName(`view ${id}`),
        value: VIEW_LABELS[id],
        checked: api.prefs.view === id,
        exclusive: true,
        insert: optionDraft("/view", id),
        token: id,
        activate: () => {
          commitExclusive(() => api.setView(id));
        },
      })),
    [api, commitExclusive],
  );

  const densityRows = useMemo(
    (): MenuRow[] =>
      TRACE_DENSITIES.map((id) => ({
        id,
        label: slashName(`density ${id}`),
        value: TRACE_DENSITY_LABELS[id],
        checked: api.prefs.density === id,
        exclusive: true,
        insert: optionDraft("/density", id),
        token: id,
        activate: () => {
          commitExclusive(() => api.setDensity(id));
        },
      })),
    [api, commitExclusive],
  );

  const themeRows = useMemo((): MenuRow[] => {
    const state = currentThemeState(api);
    const current = matchThemeStep(state.preference, state.palette, state.resolved);
    return themeCycle().map((step) => ({
      id: step.id,
      label: slashName(`theme ${step.palette} ${step.mode}`),
      value: step.label,
      checked: current.id === step.id,
      exclusive: true,
      insert: slashName(`theme ${step.palette} ${step.mode}`),
      token: `${step.palette} ${step.mode}`,
      activate: () => {
        commitExclusive(() => {
          if (api.setTheme && current.id === step.id) {
            // On a host that owns the theme (an embed), the checked row drops
            // the visitor's pick, so the chat follows the parent / tenant again.
            applyThemePick(api, "auto", step.palette);
          } else {
            // Document theme (the app): any row, the checked one included,
            // pins that mode and palette, as before 2.6.6.
            applyThemePick(api, step.mode, step.palette);
          }
        });
      },
    }));
  }, [api, commitExclusive]);

  const thinkingRows = useMemo(
    (): MenuRow[] =>
      THINKING_MODES.map((id) => ({
        id,
        label: slashName(`thinking ${id}`),
        value: THINKING_LABELS[id] ?? "",
        checked: api.prefs.thinking === id,
        exclusive: true,
        insert: optionDraft("/thinking", id),
        token: id,
        activate: () => {
          commitExclusive(() => api.setThinking(id));
        },
      })),
    [api, commitExclusive],
  );

  const toggleTool = useCallback(
    (id: string) => {
      if (id === "digisearch") api.setDigisearch(!api.prefs.digisearch);
      else if (id === "digivault") api.setVault(!api.prefs.vault);
      else if (id === "websearch") api.setWebSearch(!api.prefs.webSearch);
      else api.setExtraTool(id, !api.extraToolOn(id));
    },
    [api],
  );

  const commitMcpDraft = useCallback(
    (next: SessionMcpConfig) => {
      const id = next.id.trim().toLowerCase();
      const draft = { ...next, id: next.source === "operator" ? next.id : id };
      setMcpDraft(draft);
      if (!MCP_ID_RE.test(id)) {
        setMcpError(next.id.trim() ? "id must be a lowercase slug (a-z, 0-9, _, -)" : null);
        return;
      }
      setMcpError(null);
      api.setMcpConfig(draft, mcpDraft.source === "session" ? mcpDraft.id : id);
    },
    [api, mcpDraft.id, mcpDraft.source],
  );

  useEffect(() => {
    return listenMcpOAuthResult((msg) => {
      const draft = mcpDraftRef.current;
      if (msg.id && draft.id && msg.id !== draft.id) return;
      setMcpOAuthBusy(false);
      if (msg.error) {
        setMcpError(msg.error);
        return;
      }
      if (msg.accessToken) {
        commitMcpDraft({ ...draft, token: msg.accessToken });
      }
    });
  }, [commitMcpDraft]);

  const authenticateMcp = useCallback(async () => {
    const draft = mcpDraftRef.current;
    if (!MCP_ID_RE.test(draft.id)) {
      setMcpError("id must be a lowercase slug (a-z, 0-9, _, -)");
      return;
    }
    if (draft.source === "session" && !draft.url.trim()) {
      setMcpError("Add a URL before Authenticate.");
      return;
    }
    setMcpOAuthBusy(true);
    setMcpError(null);
    try {
      await startMcpOAuth({
        id: draft.id,
        url: draft.source === "session" ? draft.url : undefined,
        clientId: draft.extra.client_id,
        scopes: draft.extra.scopes,
      });
    } catch (e) {
      setMcpOAuthBusy(false);
      setMcpError(e instanceof Error ? e.message : "Could not start OAuth.");
    }
  }, []);

  const toolsRows = useMemo((): MenuRow[] => {
    if (!toolRows.length) {
      return [
        {
          id: "tools-none",
          label: "No tools",
          value: "This install",
          activate: () => {
            if (kind === "tools") onClose();
            else {
              setView("main");
            }
          },
        },
      ];
    }
    const readOnly = api.toolControl === "agent" || api.toolControl === "locked";
    // The agent owns its tools: always on, never toggled here.
    const agent = api.toolControl === "agent";
    // A file-system-like tree: the service as `/slash`, its tools under it.
    return toolRows.flatMap((t): MenuRow[] => {
      const on = agent || connectedToolIsOn(t.id, toolOnInput);
      const state = on ? "On" : "Off";
      const group: MenuRow = {
        id: t.id,
        label: slashName(t.slash),
        value: state,
        checked: on,
        insert: optionDraft("/tools", t.slash),
        token: t.slash,
        activate: () => {
          if (readOnly) return;
          toggleTool(t.id);
        },
      };
      const configured = t.tools ?? [];
      const count = configured.length || (t.builtinTools?.length ?? 0);
      // A tool closes its branch when it is the last one, or the last one in
      // its sub-header group.
      const branchAt = (i: number): MenuRow["branch"] =>
        i === count - 1 || (configured[i]?.group ?? "") !== (configured[i + 1]?.group ?? "")
          ? "last"
          : "mid";
      const subs = configured.flatMap((sub, i): MenuRow[] => {
        const subOn = agent || (on && api.extraToolOn(sub.id));
        const subLabel = sub.id;
        const groupName = sub.group?.trim() ?? "";
        const opensGroup = groupName !== "" && groupName !== (configured[i - 1]?.group?.trim() ?? "");
        const heading: MenuRow[] = opensGroup
          ? [
              {
                id: `${t.id}::group::${groupName}`,
                label: groupName,
                value: "",
                heading: true,
                activate: () => {},
              },
            ]
          : [];
        return [
          ...heading,
          {
            id: `${t.id}::${sub.id}`,
            label: subLabel,
            branch: branchAt(i),
            value: subOn ? "On" : "Off",
            checked: subOn,
            insert: optionDraft("/tools", subLabel),
            token: subLabel,
            activate: () => {
              if (readOnly || !on) return;
              api.setExtraTool(sub.id, !api.extraToolOn(sub.id));
            },
          },
        ];
      });
      // Built-in tools follow the service switch, so they carry its state but
      // no switch of their own.
      const builtins = configured.length
        ? []
        : (t.builtinTools ?? []).map(
            (sub, i): MenuRow => ({
              id: `${t.id}::${sub.id}`,
              label: sub.id,
              branch: branchAt(i),
              value: state,
              token: sub.id,
              activate: () => {},
            }),
          );
      return [group, ...subs, ...builtins];
    });
  }, [api, kind, onClose, toggleTool, toolOnInput, toolRows]);

  const mcpRows = useMemo((): MenuRow[] => {
    const readOnly = api.toolControl === "agent" || api.toolControl === "locked";
    const agent = api.toolControl === "agent";
    if (agent && mcpConfigs.length === 0) {
      return toolRows.map((t) => ({
        id: t.id,
        label: t.id,
        value: "On",
        insert: optionDraft("/mcp", t.id),
        token: t.id,
        activate: () => {},
      }));
    }
    const rows: MenuRow[] = mcpConfigs.map((s) => {
      const status = mcpStatus(s, api.extraToolOn(s.id));
      const label = s.id;
      return {
        id: s.id,
        label,
        value: agent ? "On" : mcpStatusLabel(status),
        insert: optionDraft("/mcp", label),
        token: label,
        activate: () => {
          if (readOnly) return;
          setMcpDraft(s);
          setMcpError(null);
          setMcpSuggestIndex(-1);
          setMcpIdDropdownOpen(false);
          setView("mcp-edit");
        },
      };
    });
    if (api.allowAddMcp && !readOnly) {
      rows.push({
        id: "mcp-new",
        label: slashName("mcp new"),
        value: "Add",
        activate: () => {
          setMcpDraft(emptyMcpConfig());
          setMcpError(null);
          setMcpSuggestIndex(-1);
          setMcpIdDropdownOpen(false);
          setView("mcp-edit");
        },
      });
    }
    return rows;
  }, [api, mcpConfigs, toolRows]);

  const mcpSuggestions = useMemo(
    () => (mcpDraft.source === "session" ? wellKnownMcpSuggestions(mcpDraft.id) : []),
    [mcpDraft.id, mcpDraft.source],
  );
  const mcpSuggestionGroups = useMemo(() => wellKnownMcpGrouped(mcpSuggestions), [mcpSuggestions]);
  const mcpIdListOpen =
    mcpIdDropdownOpen && mcpDraft.source === "session" && mcpSuggestions.length > 0;

  const applyMcpSuggestion = useCallback(
    (id: string) => {
      commitMcpDraft(applyWellKnownMcp(mcpDraft, id));
      setMcpSuggestIndex(-1);
      setMcpIdDropdownOpen(false);
    },
    [commitMcpDraft, mcpDraft],
  );

  const closeMcpIdDropdown = useCallback(() => {
    setMcpIdDropdownOpen(false);
    setMcpSuggestIndex(-1);
  }, []);

  const activateProvider = useCallback(
    async (model: string) => {
      if (!onActivateProvider) {
        setProviderError("This surface does not accept a provider key.");
        return;
      }
      const format = validateBYOKKey(keyDraft, providerPick);
      if (format) {
        setProviderError(format);
        setView("provider-key");
        return;
      }
      const modelErr = validateBYOKModel(model, providerPick);
      if (modelErr) {
        setProviderError(modelErr);
        setView("provider-model");
        return;
      }
      setProviderPending(true);
      setProviderError(null);
      const result = await pingByokKey(keyDraft, providerPick, model);
      if (!aliveRef.current) return;
      setProviderPending(false);
      const refuse = byokActivationGate(result);
      if (refuse) {
        setProviderError(refuse);
        return;
      }
      onActivateProvider(keyDraft.trim(), providerPick, model.trim());
      onClose();
    },
    [keyDraft, onActivateProvider, onClose, providerPick],
  );

  const submitProviderKey = useCallback(() => {
    const err = validateBYOKKey(keyDraft, providerPick);
    if (err) {
      setProviderError(err);
      return;
    }
    setProviderError(null);
    if (!byokRequiresModel(providerPick)) {
      void activateProvider("");
      return;
    }
    setView("provider-model");
    setCustomModel(false);
    if (wantsProviderKeyPing(providerPick)) {
      setProviderPending(true);
      void pingByokKey(keyDraft, providerPick, "", { requireModel: false }).then((result) => {
        if (!aliveRef.current) return;
        setProviderPending(false);
        if (result.ok && result.models?.length) setLiveModels(result.models);
      });
    }
  }, [activateProvider, keyDraft, providerPick]);

  const providerRows = useMemo((): MenuRow[] => {
    // The house backend is a provider choice too: selecting it drops any BYOK
    // key and returns routing to Cheaper Inference.
    const rows: MenuRow[] = [
      {
        id: HOUSE_BACKEND_ID,
        label: slashName(HOUSE_BACKEND_ID),
        value: "Default · no key",
        checked: !providerActive,
        exclusive: true,
        activate: () => {
          onClearProvider?.();
          onClose();
        },
      },
      ...PROVIDER_MENU_ORDER.map((id) => ({
        id,
        label: slashName(id),
        value: `${providerDisplayName(id)} · own key`,
        checked: providerActive?.provider === id,
        exclusive: true,
        activate: () => {
          setProviderPick(id);
          setKeyDraft("");
          setModelDraft("");
          setCustomModel(false);
          setProviderError(null);
          setLiveModels(undefined);
          setView("provider-key");
        },
      })),
    ];
    return rows;
  }, [onClearProvider, onClose, providerActive, providerPick]);

  const providerModelRows = useMemo((): MenuRow[] => {
    return providerModelChoices(providerPick, liveModels).map((m) => ({
      id: m.id || "default",
      label: m.label,
      value: m.id && m.id !== CUSTOM_PROVIDER_MODEL ? m.id : "",
      activate: () => {
        if (m.id === CUSTOM_PROVIDER_MODEL) {
          setCustomModel(true);
          setModelDraft("");
          return;
        }
        void activateProvider(m.id);
      },
    }));
  }, [activateProvider, liveModels, providerPick]);

  const rows =
    view === "main"
      ? mainRows
      : view === "language"
        ? languageRows
        : view === "effort"
          ? effortRows
          : view === "view"
            ? viewRows
            : view === "density"
              ? densityRows
              : view === "thinking"
              ? thinkingRows
              : view === "theme"
                ? themeRows
                : view === "tools"
                    ? toolsRows
                    : view === "mcp"
                      ? mcpRows
                      : view === "mcp-edit"
                        ? []
                        : view === "provider"
                          ? providerRows
                          : view === "provider-model"
                            ? providerModelRows
                            : view === "provider-key"
                              ? []
                              : view === "search-engine"
                                ? engineRows
                                : view === "help"
                                  ? []
                                  : modelRows;
  const paletteFilter =
    view === "main" ||
    view === "help" ||
    view === "mcp-edit" ||
    view === "provider-key" ||
    (view === "provider-model" && customModel)
      ? ""
      : (api.paletteQuery ?? "");
  const selection = submenuRows(
    rows.map((row) => ({ ...row, token: row.token ?? row.label })),
    paletteFilter,
  );
  const shown = selection.rows;
  const title =
    view === "language"
      ? "/language"
      : view === "models"
        ? "/models"
        : view === "effort"
          ? "/effort"
          : view === "view"
            ? "/view"
            : view === "density"
              ? "/density"
              : view === "theme"
              ? "/theme"
              : view === "thinking"
                ? "/thinking"
                : view === "tools"
                  ? "/tools"
                  : view === "mcp" || view === "mcp-edit"
                    ? "/mcp"
                    : view === "provider" || view === "provider-key" || view === "provider-model"
                      ? "/provider"
                      : view === "search-engine"
                        ? "/search-engine"
                        : view === "help"
                          ? "/help"
                          : "Settings";

  const safeCursor = shown.length ? Math.min(cursor, shown.length - 1) : 0;
  if (safeCursor !== cursor) setCursor(safeCursor);

  /**
   * The cursor belongs to the page, not to the moment the menu opened: a
   * page with a current value opens on it, so Enter commits what is set
   * instead of the first row. The seed is read from the rows the page
   * renders, so the list a page shows and the list it indexes are the same
   * list by construction.
   */
  if (seededView !== view) {
    const from = seededView;
    setSeededView(view);
    let seed = cursorOnCurrentRow(shown);
    if (view === "provider" && (from === "provider-key" || from === "provider-model")) {
      // Back from a provider form: land on the provider the user opened, not
      // on the one that happens to be connected.
      const picked = providerRows.findIndex((row) => row.id === providerPick);
      if (picked >= 0) seed = picked;
    }
    setCursor(seed);
  }
  const filterKey = `${view}\0${paletteFilter}`;
  const [appliedFilter, setAppliedFilter] = useState(filterKey);
  if (appliedFilter !== filterKey) {
    setAppliedFilter(filterKey);
    if (selection.cursor >= 0) setCursor(selection.cursor);
  }

  // Form pages own the arrow keys and read-only pages have no rows; neither
  // can advertise "↑↓ navigate". Only the back gesture is true there.
  const formPage =
    view === "provider-key" || (view === "provider-model" && customModel) || view === "mcp-edit";
  const canNavigate = shown.length > 0 && !formPage && view !== "help";

  const runRow = useCallback(
    (row: MenuRow | undefined) => {
      if (!row) return;
      if (row.insert) api.setComposerDraft?.(row.insert);
      row.activate();
    },
    [api],
  );

  useEffect(() => {
    if (!echoArmed.current) return;
    echoArmed.current = false;
    const row = shown[cursor];
    if (row?.insert) api.setComposerDraft?.(row.insert);
  }, [api, cursor, shown]);

  const move = useCallback(
    (delta: number) => {
      if (!shown.length) return;
      echoArmed.current = true;
      setCursor((c) => stepSelectable(c, delta, shown));
    },
    [shown],
  );

  const goBack = useCallback(() => {
    // A custom-model draft is a sub-state of provider-model, not a page.
    if (view === "provider-model" && customModel) {
      setCustomModel(false);
      return;
    }
    const parent = MENU_PARENT[view];
    if (!parent) {
      if (api.composerDraftBound && kind === "settings") {
        api.setComposerDraft?.("/settings");
        return;
      }
      onClose();
      return;
    }
    const back = PANE_BACK_TOKEN[view];
    if (parent === "main" && api.composerDraftBound && back) {
      api.setComposerDraft?.(back);
      return;
    }
    if (view === "mcp-edit") {
      setMcpIdDropdownOpen(false);
      setMcpSuggestIndex(-1);
      setMcpError(null);
    }
    // The page we land on seeds its own cursor (the current value, or the
    // provider row the user drilled into).
    setView(parent);
  }, [api, customModel, kind, onClose, view]);

  useEffect(() => {
    if (view === "provider-key") keyInputRef.current?.focus();
    if (view === "provider-model" && customModel) customModelRef.current?.focus();
  }, [view, customModel]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (view === "mcp-edit" && mcpIdDropdownOpen) {
          closeMcpIdDropdown();
          return;
        }
        goBack();
        return;
      }
      // mcp-edit owns its keys (id-list arrows/Enter, auth radios). Do not steal them.
      if (formPage) return;
      if (event.key === "ArrowDown") {
        event.preventDefault();
        event.stopPropagation();
        move(1);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        event.stopPropagation();
        move(-1);
        return;
      }
      // Left/right are actions, not scrolling: right submits like Enter and
      // left goes back like Escape. The hint row spells this out.
      if (event.key === "ArrowRight") {
        event.preventDefault();
        event.stopPropagation();
        runRow(shown[cursor]);
        return;
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        event.stopPropagation();
        goBack();
        return;
      }
      if (event.key === "Home") {
        event.preventDefault();
        event.stopPropagation();
        echoArmed.current = true;
        setCursor(selectableIndexes(shown)[0] ?? 0);
        return;
      }
      if (event.key === "End") {
        event.preventDefault();
        event.stopPropagation();
        echoArmed.current = true;
        const selectable = selectableIndexes(shown);
        setCursor(selectable[selectable.length - 1] ?? Math.max(0, shown.length - 1));
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        event.stopPropagation();
        runRow(shown[cursor]);
      }
    },
    [closeMcpIdDropdown, cursor, formPage, goBack, mcpIdDropdownOpen, move, runRow, shown, view],
  );

  useEffect(() => {
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [onKeyDown]);

  // Keep the arrow-key cursor inside the scroll viewport. Without this the
  // cursor walks past the fold on long pages (language, models) and the menu
  // looks frozen because the row it moved to is out of sight.
  useEffect(() => {
    const body = menuBodyRef.current;
    if (!body) return;
    const row = body.querySelector<HTMLElement>('[data-cursor="true"]');
    if (!row) return;
    const rowRect = row.getBoundingClientRect();
    const bodyRect = body.getBoundingClientRect();
    if (rowRect.top < bodyRect.top) {
      body.scrollTop -= bodyRect.top - rowRect.top;
    } else if (rowRect.bottom > bodyRect.bottom) {
      body.scrollTop += rowRect.bottom - bodyRect.bottom;
    }
  }, [cursor, view]);

  // The suggestion list is absolutely positioned against its own anchor, so
  // it has to follow the id field: the field scrolls inside the menu body
  // and the page scrolls under the menu.
  const placeMcpIdDropdown = useCallback(() => {
    const field = mcpIdFieldRef.current;
    if (!field) return;
    const rect = field.getBoundingClientRect();
    setMcpIdAnchor((prev) => {
      const top = Math.round(rect.bottom);
      const left = Math.round(rect.left);
      const width = Math.round(rect.width);
      if (prev && prev.top === top && prev.left === left && prev.width === width) return prev;
      return { top, left, width };
    });
  }, []);

  useEffect(() => {
    if (!mcpIdListOpen) return;
    placeMcpIdDropdown();
    window.addEventListener("scroll", placeMcpIdDropdown, true);
    window.addEventListener("resize", placeMcpIdDropdown);
    return () => {
      window.removeEventListener("scroll", placeMcpIdDropdown, true);
      window.removeEventListener("resize", placeMcpIdDropdown);
    };
  }, [mcpIdListOpen, placeMcpIdDropdown]);

  const onRowKey = (event: ReactKeyboardEvent, index: number) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      runRow(shown[index]);
    }
  };

  const formView =
    view === "provider-key" || (view === "provider-model" && customModel) || view === "mcp-edit";

  // The suggestion list lives in a zero-height anchor that follows the id
  // field, so it overlays the menu instead of being clipped by the menu
  // body's scroll box. The anchor is a direct child of the document body, so
  // no ancestor of the menu can clip the list.
  const mcpIdSuggestions =
    mcpIdListOpen && mcpIdAnchor && typeof document !== "undefined"
      ? createPortal(
          <div
            data-mcp-id-anchor
            className="fixed z-[60]"
            style={{
              top: mcpIdAnchor.top,
              left: mcpIdAnchor.left,
              width: mcpIdAnchor.width,
              height: 0,
            }}
          >
            <div
              id="mcp-id-suggestions"
              role="listbox"
              aria-labelledby="mcp-id-label"
              data-mcp-id-dropdown
              className="border-hair bg-surface absolute inset-x-0 top-full z-20 mt-px max-h-40 overflow-y-auto overscroll-contain rounded-none border"
              onMouseDown={(e) => e.preventDefault()}
            >
              {mcpSuggestionGroups.map((g) => (
                <div key={g.group}>
                  <div className="text-ink-mute px-3 py-1 text-xs">{g.group}</div>
                  {g.servers.map((row) => {
                    const index = mcpSuggestions.findIndex((s) => s.id === row.id);
                    const highlighted = index === mcpSuggestIndex;
                    return (
                      <button
                        key={row.id}
                        id={`mcp-suggest-${row.id}`}
                        type="button"
                        role="option"
                        tabIndex={-1}
                        aria-label={row.id}
                        aria-selected={highlighted}
                        data-cursor={highlighted ? "true" : undefined}
                        className={`${MCP_SUGGEST_ROW_CLASS} ${highlighted ? "bg-surface-2/50" : ""}`}
                        ref={(node) => {
                          if (!highlighted || !node) return;
                          const root = node.closest("[data-mcp-id-dropdown]");
                          if (!(root instanceof HTMLElement)) return;
                          const n = node.getBoundingClientRect();
                          const r = root.getBoundingClientRect();
                          if (n.bottom > r.bottom) root.scrollTop += n.bottom - r.bottom;
                          else if (n.top < r.top) root.scrollTop -= r.top - n.top;
                        }}
                        onMouseEnter={() => setMcpSuggestIndex(index)}
                        onClick={() => applyMcpSuggestion(row.id)}
                      >
                        <span className="min-w-0 flex-1 font-medium break-words [overflow-wrap:anywhere]">
                          {row.id}
                        </span>
                        <span className="text-ink-mute min-w-0 truncate text-right text-xs">
                          {wellKnownMcpHost(row.url) || row.auth}
                        </span>
                      </button>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>,
          document.body,
        )
      : null;

  const body = (
    <div
      className="dc-composer-menu aui-composer-trigger-popover absolute inset-x-0 bottom-full z-50 mb-1 w-full overflow-hidden rounded-none border"
      data-thread-skin="digichat"
      data-embed-settings
      data-embed-composer-menu
      role={formView ? "dialog" : "menu"}
      aria-label={title}
    >
      <div className="relative min-h-0">
        <div
          ref={menuBodyRef}
          className="dc-composer-menu-body flex max-h-[min(50vh,22rem)] flex-col overflow-y-auto pt-0.5 pb-1.5"
        >
          {view === "provider-key" ? (
            <Label className="flex flex-col items-stretch gap-1 px-3 py-1.5" htmlFor={keyFormId}>
              <span className="text-ink-mute text-xs">Paste API key, then Enter</span>
              <Input
                ref={keyInputRef}
                id={keyFormId}
                type="password"
                value={keyDraft}
                placeholder={providerKeyPlaceholder(providerPick)}
                autoComplete="off"
                spellCheck={false}
                aria-invalid={Boolean(providerError)}
                className="border-hair bg-transparent w-full rounded-none border px-2 py-1.5 font-mono text-sm outline-none h-auto"
                onChange={(e) => {
                  setKeyDraft(e.target.value);
                  setProviderError(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    submitProviderKey();
                  }
                }}
              />
            </Label>
          ) : null}
          {view === "provider-model" && customModel ? (
            <Label className="flex flex-col items-stretch gap-1 px-3 py-1.5">
              <span className="text-ink-mute text-xs">Model slug, then Enter</span>
              <Input
                ref={customModelRef}
                type="text"
                value={modelDraft}
                autoComplete="off"
                spellCheck={false}
                className="border-hair bg-transparent w-full rounded-none border px-2 py-1.5 font-mono text-sm outline-none h-auto"
                onChange={(e) => {
                  setModelDraft(e.target.value);
                  setProviderError(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void activateProvider(modelDraft);
                  }
                }}
              />
            </Label>
          ) : null}
          {view === "mcp-edit" ? (
            <div className="flex flex-col gap-2 px-3 py-1.5">
              <pre className="border-hair text-ink-mute max-h-32 overflow-auto border px-2 py-1.5 font-mono text-[11px] leading-4">
                {mcpConfigJson(mcpDraft)}
              </pre>
              <div className="flex flex-col items-stretch gap-1">
                <span className="text-ink-mute text-xs" id="mcp-id-label">
                  id
                </span>
                <div className="relative z-10" data-mcp-id-field ref={mcpIdFieldRef}>
                  <Input
                    type="text"
                    value={mcpDraft.id}
                    disabled={mcpDraft.source === "operator"}
                    placeholder="linear"
                    autoComplete="off"
                    spellCheck={false}
                    role="combobox"
                    aria-labelledby="mcp-id-label"
                    aria-autocomplete="list"
                    aria-expanded={mcpIdListOpen}
                    aria-controls={mcpDraft.source === "session" ? "mcp-id-suggestions" : undefined}
                    aria-activedescendant={
                      mcpIdListOpen && mcpSuggestIndex >= 0 && mcpSuggestions[mcpSuggestIndex]
                        ? `mcp-suggest-${mcpSuggestions[mcpSuggestIndex]!.id}`
                        : undefined
                    }
                    className="border-hair bg-transparent w-full rounded-none border px-2 py-1 font-mono text-sm outline-none disabled:opacity-60 h-auto"
                    onFocus={() => {
                      if (mcpDraft.source !== "session") return;
                      placeMcpIdDropdown();
                      setMcpIdDropdownOpen(true);
                    }}
                    onBlur={(e) => {
                      const root = e.currentTarget.closest("[data-mcp-id-field]");
                      if (e.relatedTarget instanceof Node && root?.contains(e.relatedTarget))
                        return;
                      closeMcpIdDropdown();
                    }}
                    onChange={(e) => {
                      setMcpSuggestIndex(-1);
                      if (mcpDraft.source === "session") {
                        placeMcpIdDropdown();
                        setMcpIdDropdownOpen(true);
                      }
                      commitMcpDraft(applyWellKnownMcp(mcpDraft, e.target.value));
                    }}
                    onKeyDown={(e) => {
                      if (mcpDraft.source === "operator") return;
                      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                        if (!mcpSuggestions.length) return;
                        e.preventDefault();
                        e.stopPropagation();
                        if (!mcpIdDropdownOpen) {
                          placeMcpIdDropdown();
                          setMcpIdDropdownOpen(true);
                          setMcpSuggestIndex(e.key === "ArrowDown" ? 0 : mcpSuggestions.length - 1);
                          return;
                        }
                        const delta = e.key === "ArrowDown" ? 1 : -1;
                        setMcpSuggestIndex((i) => {
                          if (i < 0) return delta === 1 ? 0 : mcpSuggestions.length - 1;
                          return nextPaletteIndex(i, delta, mcpSuggestions.length);
                        });
                        return;
                      }
                      if (e.key === "Enter") {
                        if (!mcpIdListOpen) return;
                        const hit =
                          mcpSuggestIndex >= 0 ? mcpSuggestions[mcpSuggestIndex] : undefined;
                        if (!hit) return;
                        e.preventDefault();
                        e.stopPropagation();
                        applyMcpSuggestion(hit.id);
                      }
                    }}
                  />
                  {mcpIdSuggestions}
                </div>
              </div>
              <Label className="flex flex-col items-stretch gap-1">
                <span className="text-ink-mute text-xs">label</span>
                <Input
                  type="text"
                  value={mcpDraft.label}
                  autoComplete="off"
                  spellCheck={false}
                  className="border-hair bg-transparent w-full rounded-none border px-2 py-1 font-mono text-sm outline-none h-auto"
                  onChange={(e) => commitMcpDraft({ ...mcpDraft, label: e.target.value })}
                />
              </Label>
              {mcpDraft.source === "session" ? (
                <Label className="flex flex-col items-stretch gap-1">
                  <span className="text-ink-mute text-xs">url</span>
                  <Input
                    type="url"
                    value={mcpDraft.url}
                    placeholder="https://…"
                    autoComplete="off"
                    spellCheck={false}
                    className="border-hair bg-transparent w-full rounded-none border px-2 py-1 font-mono text-sm outline-none h-auto"
                    onChange={(e) => commitMcpDraft({ ...mcpDraft, url: e.target.value })}
                  />
                </Label>
              ) : (
                <p className="text-ink-mute text-xs">url is operator-managed (BFF)</p>
              )}
              <div className="flex flex-col items-stretch gap-1">
                <span className="text-ink-mute text-xs" id="mcp-auth-label">
                  auth
                </span>
                <div
                  role="radiogroup"
                  aria-labelledby="mcp-auth-label"
                  className="border-hair flex border"
                  onKeyDown={(e) => {
                    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
                    e.preventDefault();
                    e.stopPropagation();
                    const delta = e.key === "ArrowRight" ? 1 : -1;
                    const next = cycleMcpAuth(mcpDraft.auth, delta);
                    commitMcpDraft({ ...mcpDraft, auth: next });
                    queueMicrotask(() => {
                      document.getElementById(`mcp-auth-${next}`)?.focus();
                    });
                  }}
                >
                  {MCP_AUTH.map((kind, index) => {
                    const selected = mcpDraft.auth === kind;
                    return (
                      <button
                        key={kind}
                        id={`mcp-auth-${kind}`}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        tabIndex={selected ? 0 : -1}
                        className={`min-w-0 flex-1 px-2 py-1 font-mono text-xs outline-none outline-offset-[-1px] ${
                          index > 0 ? "border-hair border-l" : ""
                        } ${selected ? "bg-surface-2 text-ink" : "text-ink-mute hover:bg-surface-2/50 hover:text-ink"}`}
                        onClick={() => commitMcpDraft({ ...mcpDraft, auth: kind })}
                      >
                        {kind}
                      </button>
                    );
                  })}
                </div>
              </div>
              {mcpDraft.auth === "oauth" ? (
                <div className="flex flex-col items-stretch gap-1">
                  <span className="text-ink-mute text-xs">token / oauth client secret</span>
                  <div className="flex min-w-0 items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-auto shrink-0 whitespace-nowrap border-hair px-2 py-1"
                      disabled={mcpOAuthBusy}
                      onClick={() => void authenticateMcp()}
                    >
                      {mcpOAuthBusy ? "Authenticating…" : "Authenticate"}
                    </Button>
                    <span className="text-ink-mute whitespace-nowrap text-xs">or</span>
                    <Input
                      type="password"
                      value={mcpDraft.token}
                      placeholder="OAuth token"
                      autoComplete="off"
                      spellCheck={false}
                      className="border-hair bg-transparent min-w-0 flex-1 rounded-none border px-2 py-1 font-mono text-sm outline-none h-auto"
                      onChange={(e) => commitMcpDraft({ ...mcpDraft, token: e.target.value })}
                    />
                  </div>
                </div>
              ) : mcpDraft.auth !== "none" ? (
                <Label className="flex flex-col items-stretch gap-1">
                  <span className="text-ink-mute text-xs">token</span>
                  <Input
                    type="password"
                    value={mcpDraft.token}
                    placeholder="Bearer token"
                    autoComplete="off"
                    spellCheck={false}
                    className="border-hair bg-transparent w-full rounded-none border px-2 py-1 font-mono text-sm outline-none h-auto"
                    onChange={(e) => commitMcpDraft({ ...mcpDraft, token: e.target.value })}
                  />
                </Label>
              ) : null}
              <div className="flex flex-col items-stretch gap-1">
                <span className="text-ink-mute text-xs">other</span>
                {Object.entries(mcpDraft.extra).map(([key, value]) => (
                  <Label key={key} className="flex flex-col items-stretch gap-1">
                    <span className="text-ink-mute text-xs">{key}</span>
                    <Input
                      type="text"
                      value={value}
                      autoComplete="off"
                      spellCheck={false}
                      className="border-hair bg-transparent w-full rounded-none border px-2 py-1 font-mono text-sm outline-none h-auto"
                      onChange={(e) =>
                        commitMcpDraft({
                          ...mcpDraft,
                          extra: { ...mcpDraft.extra, [key]: e.target.value },
                        })
                      }
                    />
                  </Label>
                ))}
                <div className="flex gap-2">
                  <Input
                    type="text"
                    value={mcpFieldName}
                    placeholder="field"
                    autoComplete="off"
                    spellCheck={false}
                    className="border-hair bg-transparent min-w-0 flex-1 rounded-none border px-2 py-1 font-mono text-sm outline-none h-auto"
                    onChange={(e) => setMcpFieldName(e.target.value)}
                  />
                  <Input
                    type="text"
                    value={mcpFieldValue}
                    placeholder="value"
                    autoComplete="off"
                    spellCheck={false}
                    className="border-hair bg-transparent min-w-0 flex-1 rounded-none border px-2 py-1 font-mono text-sm outline-none h-auto"
                    onChange={(e) => setMcpFieldValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key !== "Enter") return;
                      e.preventDefault();
                      const key = mcpFieldName.trim();
                      if (
                        !key ||
                        key === "id" ||
                        key === "label" ||
                        key === "url" ||
                        key === "auth" ||
                        key === "token"
                      ) {
                        return;
                      }
                      commitMcpDraft({
                        ...mcpDraft,
                        extra: { ...mcpDraft.extra, [key]: mcpFieldValue },
                      });
                      setMcpFieldName("");
                      setMcpFieldValue("");
                    }}
                  />
                </div>
              </div>
              {mcpError ? (
                <p className="text-danger text-xs" role="alert">
                  {mcpError}
                </p>
              ) : null}
            </div>
          ) : null}
          {view === "help" ? (
            <div className="flex flex-col gap-2 px-3 py-2 text-xs leading-relaxed" data-embed-help>
              <p className="text-ink-mute">
                Ask about OCC policies, procedures and help articles, search internal notes, or
                check live support tickets.
              </p>
              <div className="flex flex-col gap-1">
                <span className="text-ink-mute text-[11px] uppercase tracking-wide">
                  Try asking
                </span>
                <span>How do I raise a support ticket?</span>
                <span>What is our data retention policy?</span>
                <span>Summarise my open support tickets.</span>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-ink-mute text-[11px] uppercase tracking-wide">
                  Commands
                </span>
                <span className="font-mono">
                  /models · /language · /tools · /mcp · /settings · /theme · /new
                </span>
              </div>
              <span className="text-ink-mute">Enter sends · Shift+Enter adds a line</span>
              <span>
                Need a person?{" "}
                <a className="underline underline-offset-2" href="mailto:contact@digithings.ai">
                  contact@digithings.ai
                </a>
              </span>
            </div>
          ) : null}
          {view !== "provider-key" &&
          !(view === "provider-model" && customModel) &&
          view !== "mcp-edit" &&
          view !== "help"
            ? shown.map((row, index) => {
                if (row.heading) {
                  return (
                    <div
                      key={row.id}
                      role="presentation"
                      className="text-ink-mute flex items-baseline gap-2 px-2 pt-2 pb-0.5 text-[11px] uppercase tracking-wide"
                    >
                      <span>{row.label}</span>
                      {row.value ? (
                        <span className="normal-case tracking-normal">{row.value}</span>
                      ) : null}
                    </div>
                  );
                }
                const toggle =
                  typeof row.checked === "boolean" && (view === "main" || view === "tools");
                const exclusive = Boolean(row.exclusive);
                return (
                  <button
                    key={row.id}
                    id={`dc-menu-${row.id}`}
                    type="button"
                    role={toggle ? "menuitemcheckbox" : exclusive ? "menuitemradio" : "menuitem"}
                    aria-checked={typeof row.checked === "boolean" ? row.checked : undefined}
                    aria-expanded={typeof row.expanded === "boolean" ? row.expanded : undefined}
                    aria-label={row.ariaLabel}
                    data-cursor={index === cursor ? "true" : undefined}
                    className={MENU_ROW_CLASS}
                    ref={(node) => {
                      if (index === cursor) node?.scrollIntoView({ block: "nearest" });
                    }}
                    onMouseEnter={() => {
                      echoArmed.current = true;
                      setCursor(index);
                    }}
                    onClick={() => runRow(row)}
                    onKeyDown={(e) => onRowKey(e, index)}
                  >
                    {/* The user-message chevron marks the cursor on every page,
                        including a checked radio row; the value mark (diamond)
                        stays on the right, so the two never collide. */}
                    {index === cursor ? (
                      <span className="aui-menu-cursor" aria-hidden>
                        <DotMatrix state="user" className="size-3.5" />
                      </span>
                    ) : null}
                    {row.branch ? (
                      <span
                        data-slot="tools-tree-branch"
                        className="text-ink-mute shrink-0 ps-3 font-mono whitespace-pre"
                        aria-hidden
                      >
                        {(row.treePrefix ?? "") + treeBranchGlyph(row.branch)}
                      </span>
                    ) : null}
                    <span
                      className={
                        view === "tools" || view === "models"
                          ? "min-w-0 flex-1 font-mono font-medium break-words [overflow-wrap:anywhere]"
                          : "min-w-0 flex-1 font-medium break-words [overflow-wrap:anywhere]"
                      }
                    >
                      {row.label}
                    </span>
                    {row.value || (exclusive && row.checked) ? (
                      <span className="text-ink-mute ml-auto flex min-w-0 max-w-[45%] items-center justify-end gap-2 truncate text-right text-xs">
                        {row.value ? <span className="truncate">{row.value}</span> : null}
                        {exclusive && row.checked ? (
                          <span
                            data-slot="dropdown-menu-radio-item-indicator"
                            className="inline-flex shrink-0"
                          >
                            <span className="aui-menu-mark inline-flex shrink-0" aria-hidden>
                              {[0, 1, 0, 1, 1, 1, 0, 1, 0].map((on, cell) => (
                                <span
                                  key={cell}
                                  className={on ? "aui-menu-mark-cell is-on" : "aui-menu-mark-cell"}
                                />
                              ))}
                            </span>
                          </span>
                        ) : null}
                      </span>
                    ) : null}
                  </button>
                );
              })
            : null}
          {providerPending ? (
            <p className="text-ink-mute px-3 py-1 text-xs">Checking key…</p>
          ) : null}
          {providerError ? (
            <p className="text-danger px-3 py-1 text-xs" role="alert">
              {providerError}
            </p>
          ) : null}
        </div>
        <MenuScrollbar targetRef={menuBodyRef} />
      </div>
      <div className="text-ink-mute px-3 py-1 font-mono text-[0.68rem]">
        {title} · {canNavigate ? "↑↓ navigate · ⏎/→ submit · " : ""}esc/← back
      </div>
    </div>
  );

  const host = composerHost();
  if (!host) return null;
  return createPortal(body, host);
}
