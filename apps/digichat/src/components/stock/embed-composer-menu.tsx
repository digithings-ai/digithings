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
import { nextPaletteIndex } from "@digithings/digichat-ui";
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
  toolsMenuSummary,
  type SessionMcpConfig,
} from "@/components/stock/embed-mcp-flow";
import { languageSelectOptions } from "@/lib/product-slash-commands";
import { languageDisplayName } from "@/lib/languages";
import {
  byokRequiresModel,
  validateBYOKKey,
  validateBYOKModel,
  type BYOKProvider,
} from "@/hooks/use-byok-key";
import { byokActivationGate, pingByokKey } from "@/lib/byok-ping";
import {
  CLEAR_PROVIDER_ROW_ID,
  CUSTOM_PROVIDER_MODEL,
  defaultProviderPick,
  providerDisplayName,
  providerKeyPlaceholder,
  providerMenuRowIds,
  providerMenuRowIndex,
  providerModelChoices,
  sessionPickerModels,
  tryResolveProviderInput,
  wantsProviderKeyPing,
} from "@/components/stock/embed-provider-flow";
import { listenMcpOAuthResult, startMcpOAuth } from "@/components/stock/embed-mcp-oauth";
import { THINKING_MODES, VIEW_MODES } from "@/lib/view-modes";

export type ComposerMenuKind =
  | "settings"
  | "models"
  | "mcp"
  | "tools"
  | "language"
  | "effort"
  | "search-engine"
  | "view"
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
  | "thinking"
  | "tools"
  | "mcp"
  | "mcp-edit"
  | "provider"
  | "provider-key"
  | "provider-model"
  | "help";

type MenuRow = {
  id: string;
  label: string;
  value: string;
  activate: () => void;
  checked?: boolean;
  /** Single-choice list: radio disc, not On/Off. */
  exclusive?: boolean;
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

const VIEW_LABELS: Record<string, string> = {
  hidden: "Hidden · answer only",
  compact: "Compact · closed",
  balanced: "Balanced · collapse when done",
  detailed: "Detailed · stays open",
};

const THINKING_LABELS: Record<string, string> = {
  auto: "Auto · follow view",
  collapsed: "Collapsed",
  open: "Open",
};

// digichat-local composer menu rows (not the kit DropdownMenu). These carry
// their own pointer cursor because the kit owns no equivalent row.
const MCP_SUGGEST_ROW_CLASS =
  "hover:bg-muted/50 flex w-full cursor-pointer items-baseline justify-between gap-4 rounded-none px-3 py-1.5 text-start text-sm outline-none outline-offset-[-1px]"; // canon-allow: digichat-local composer menu; kit owns no equivalent

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
  const languageCodes = useMemo(() => languages.map((o) => o.value), [languages]);

  const [view, setView] = useState<MenuView>(() => initialView(kind));
  const [cursor, setCursor] = useState(0);
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
  const keyInputRef = useRef<HTMLInputElement>(null);
  const customModelRef = useRef<HTMLInputElement>(null);
  const aliveRef = useRef(true);
  const mcpDraftRef = useRef(mcpDraft);
  const keyFormId = useId();
  const openKey = `${kind}\0${providerSeed ?? ""}\0${mcpSeed ?? ""}`;
  const [appliedOpen, setAppliedOpen] = useState("");

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
      setCursor(0);
    } else if (mcpOpened === "new") {
      setMcpDraft(emptyMcpConfig());
      setView("mcp-edit");
      setCursor(0);
    } else if (typeof mcpOpened === "string") {
      const hit =
        connectedMcpConfigs(api.mcpServers, api.prefs.mcpCustom).find((s) => s.id === mcpOpened) ??
        applyWellKnownMcp({ ...emptyMcpConfig(), label: mcpOpened }, mcpOpened);
      setMcpDraft(hit);
      setView("mcp-edit");
      setCursor(0);
    } else {
      setView(next);
      if (kind === "language") {
        setCursor(Math.max(0, languageCodes.indexOf(api.prefs.language)));
      } else if (kind === "effort") {
        setCursor(Math.max(0, EFFORTS.indexOf(api.prefs.effort as (typeof EFFORTS)[number])));
      } else if (kind === "search-engine") {
        setCursor(
          Math.max(
            0,
            SEARCH_ENGINES.indexOf(api.prefs.searchEngine as (typeof SEARCH_ENGINES)[number]),
          ),
        );
      } else if (kind === "view") {
        setCursor(Math.max(0, VIEW_MODES.indexOf(api.prefs.view)));
      } else if (kind === "thinking") {
        setCursor(Math.max(0, THINKING_MODES.indexOf(api.prefs.thinking)));
      } else if (kind === "provider") {
        const current = defaultProviderPick(providerActive?.provider, initialProvider);
        setProviderPick(current);
        setCursor(providerMenuRowIndex(providerActive?.provider));
      } else {
        setCursor(0);
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
  }

  const mainRows = useMemo((): MenuRow[] => {
    const rows: MenuRow[] = [];
    if (toolRows.length > 0) {
      rows.push({
        id: "tools",
        label: slashName("tools"),
        value: toolsMenuSummary(toolRows, (id) => connectedToolIsOn(id, toolOnInput)),
        activate: () => {
          setCursor(0);
          setView("tools");
        },
      });
    }
    if (mcpConfigs.length > 0 || api.allowUserMcp) {
      rows.push({
        id: "mcp",
        label: slashName("mcp"),
        value: mcpMenuSummaryFromConfigs(mcpConfigs, api.extraToolOn),
        activate: () => {
          setCursor(0);
          setView("mcp");
        },
      });
    }
    rows.push({
      id: "view",
      label: slashName("view"),
      value: api.prefs.view,
      activate: () => {
        setCursor(Math.max(0, VIEW_MODES.indexOf(api.prefs.view)));
        setView("view");
      },
    });
    rows.push({
      id: "thinking",
      label: slashName("thinking"),
      value: api.prefs.thinking,
      activate: () => {
        setCursor(Math.max(0, THINKING_MODES.indexOf(api.prefs.thinking)));
        setView("thinking");
      },
    });
    rows.push({
      id: "language",
      label: slashName("language"),
      value: languageDisplayName(api.prefs.language),
      activate: () => {
        const idx = Math.max(0, languageCodes.indexOf(api.prefs.language));
        setCursor(idx);
        setView("language");
      },
    });
    if (api.showModels) {
      rows.push({
        id: "model",
        label: slashName("models"),
        value: api.prefs.model || available[0] || "Default",
        activate: () => {
          setCursor(0);
          setView("models");
        },
      });
      rows.push({
        id: "effort",
        label: slashName("effort"),
        value: api.prefs.effort,
        activate: () => {
          setCursor(Math.max(0, EFFORTS.indexOf(api.prefs.effort as (typeof EFFORTS)[number])));
          setView("effort");
        },
      });
    }
    if (api.tenantAllowsWeb) {
      rows.push({
        id: "search-engine",
        label: slashName("search-engine"),
        value: SEARCH_ENGINE_LABELS[api.prefs.searchEngine || "auto"] ?? api.prefs.searchEngine,
        activate: () => {
          setCursor(
            Math.max(
              0,
              SEARCH_ENGINES.indexOf(api.prefs.searchEngine as (typeof SEARCH_ENGINES)[number]),
            ),
          );
          setView("search-engine");
        },
      });
    }
    if (onActivateProvider) {
      rows.push({
        id: "provider",
        label: slashName("provider"),
        value: providerActive ? providerDisplayName(providerActive.provider) : "Off",
        checked: Boolean(providerActive),
        activate: () => {
          const current = defaultProviderPick(providerActive?.provider, initialProvider);
          setProviderPick(current);
          setCursor(providerMenuRowIndex(providerActive?.provider));
          setView("provider");
        },
      });
    }
    return rows;
  }, [
    api,
    toolRows,
    toolOnInput,
    mcpConfigs,
    available,
    onActivateProvider,
    languageCodes,
    providerActive,
    initialProvider,
  ]);

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
          activate: () => {
            api.setLanguage(o.value);
            onClose();
          },
        };
      }),
    [languages, api, onClose],
  );

  const modelRows = useMemo((): MenuRow[] => {
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
            activate: () => {
              api.setModel("");
              onClose();
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
            setCursor(0);
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
        activate: () => {
          api.setModel(id);
          onPickSessionModel?.(id);
          onClose();
        },
      })),
    ];
  }, [available, api, defaultModel, onClose, onPickSessionModel, providerActive]);

  const effortRows = useMemo(
    (): MenuRow[] =>
      EFFORTS.map((id) => ({
        id,
        label: slashName(`effort ${id}`),
        value: "",
        checked: api.prefs.effort === id,
        exclusive: true,
        activate: () => {
          api.setEffort(id);
          onClose();
        },
      })),
    [api, onClose],
  );

  const engineRows = useMemo(
    (): MenuRow[] =>
      SEARCH_ENGINES.map((id) => ({
        id,
        label: slashName(`search-engine ${id}`),
        value: SEARCH_ENGINE_LABELS[id] ?? "",
        checked: (api.prefs.searchEngine || "auto") === id,
        exclusive: true,
        activate: () => {
          api.setSearchEngine(id);
          onClose();
        },
      })),
    [api, onClose],
  );

  const viewRows = useMemo(
    (): MenuRow[] =>
      VIEW_MODES.map((id) => ({
        id,
        label: slashName(`view ${id}`),
        value: VIEW_LABELS[id] ?? "",
        checked: api.prefs.view === id,
        exclusive: true,
        activate: () => {
          api.setView(id);
          onClose();
        },
      })),
    [api, onClose],
  );

  const thinkingRows = useMemo(
    (): MenuRow[] =>
      THINKING_MODES.map((id) => ({
        id,
        label: slashName(`thinking ${id}`),
        value: THINKING_LABELS[id] ?? "",
        checked: api.prefs.thinking === id,
        exclusive: true,
        activate: () => {
          api.setThinking(id);
          onClose();
        },
      })),
    [api, onClose],
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
              setCursor(0);
            }
          },
        },
      ];
    }
    // Each group row is followed by its individual tools (per-tool toggles).
    return toolRows.flatMap((t): MenuRow[] => {
      const on = connectedToolIsOn(t.id, toolOnInput);
      const group: MenuRow = {
        id: t.id,
        label: slashName(t.slash),
        value: on ? "On" : "Off",
        checked: on,
        activate: () => toggleTool(t.id),
      };
      const subs = (t.tools ?? []).map((sub): MenuRow => {
        const subOn = on && api.extraToolOn(sub.id);
        return {
          id: `${t.id}::${sub.id}`,
          label: `  ../${sub.id}`,
          value: subOn ? "On" : "Off",
          checked: subOn,
          activate: () => {
            if (!on) return;
            api.setExtraTool(sub.id, !api.extraToolOn(sub.id));
          },
        };
      });
      return [group, ...subs];
    });
  }, [api, kind, onClose, toggleTool, toolOnInput, toolRows]);

  const mcpRows = useMemo((): MenuRow[] => {
    const rows: MenuRow[] = mcpConfigs.map((s) => {
      const status = mcpStatus(s, api.extraToolOn(s.id));
      return {
        id: s.id,
        label: slashName(s.id),
        value: mcpStatusLabel(status),
        activate: () => {
          setMcpDraft(s);
          setMcpError(null);
          setMcpSuggestIndex(-1);
          setMcpIdDropdownOpen(false);
          setView("mcp-edit");
        },
      };
    });
    if (api.allowAddMcp) {
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
  }, [api, mcpConfigs]);

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
    setCursor(0);
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
    // key and returns routing to the default. The rendered order comes from
    // providerMenuRowIds(), the same list the cursor index is taken from, so a
    // prepended row can never shift the cursor.
    const rows: MenuRow[] = providerMenuRowIds().map((rowId) => {
      if (rowId === CLEAR_PROVIDER_ROW_ID) {
        return {
          id: rowId,
          label: slashName(rowId),
          value: "Default · no key",
          checked: !providerActive,
          exclusive: true,
          activate: () => {
            onClearProvider?.();
            onClose();
          },
        };
      }
      return {
        id: rowId,
        label: slashName(rowId),
        value: `${providerDisplayName(rowId)} · own key`,
        checked: providerActive?.provider === rowId,
        exclusive: true,
        activate: () => {
          setProviderPick(rowId);
          setKeyDraft("");
          setModelDraft("");
          setCustomModel(false);
          setProviderError(null);
          setLiveModels(undefined);
          setView("provider-key");
        },
      };
    });
    return rows;
  }, [onClearProvider, onClose, providerActive]);

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
            : view === "thinking"
              ? thinkingRows
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
                            : modelRows;
  const title =
    view === "language"
      ? "/language"
      : view === "models"
        ? "/models"
        : view === "effort"
          ? "/effort"
          : view === "view"
            ? "/view"
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

  const safeCursor = rows.length ? Math.min(cursor, rows.length - 1) : 0;
  if (safeCursor !== cursor) setCursor(safeCursor);

  const move = useCallback(
    (delta: number) => {
      if (!rows.length) return;
      setCursor((c) => nextPaletteIndex(c, delta, rows.length));
    },
    [rows.length],
  );

  const goBack = useCallback(() => {
    if (view === "provider-key") {
      setView("provider");
      setCursor(providerMenuRowIndex(providerPick));
      return;
    }
    if (view === "provider-model") {
      if (customModel) {
        setCustomModel(false);
        return;
      }
      setView("provider-key");
      return;
    }
    if (view === "mcp-edit") {
      setMcpIdDropdownOpen(false);
      setMcpSuggestIndex(-1);
      setView("mcp");
      setCursor(0);
      setMcpError(null);
      return;
    }
    if (view === "mcp") {
      if (kind === "mcp") {
        onClose();
        return;
      }
      setView("main");
      setCursor(0);
      return;
    }
    if (view === "tools") {
      if (kind === "tools") {
        onClose();
        return;
      }
      setView("main");
      setCursor(0);
      return;
    }
    if (view === "provider") {
      if (kind === "provider") {
        onClose();
        return;
      }
      setView("main");
      setCursor(0);
      return;
    }
    if (view !== "main") {
      setView("main");
      setCursor(0);
      return;
    }
    onClose();
  }, [customModel, kind, onClose, providerPick, view]);

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
      const typing =
        view === "provider-key" ||
        (view === "provider-model" && customModel) ||
        view === "mcp-edit";
      // mcp-edit owns its keys (id-list arrows/Enter, auth radios). Do not steal them.
      if (typing) return;
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
        rows[cursor]?.activate();
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
        setCursor(0);
        return;
      }
      if (event.key === "End") {
        event.preventDefault();
        event.stopPropagation();
        setCursor(Math.max(0, rows.length - 1));
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        event.stopPropagation();
        rows[cursor]?.activate();
      }
    },
    [
      api,
      closeMcpIdDropdown,
      cursor,
      customModel,
      goBack,
      languageCodes.length,
      mcpIdDropdownOpen,
      move,
      rows,
      view,
    ],
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

  const onRowKey = (event: ReactKeyboardEvent, index: number) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      rows[index]?.activate();
    }
  };

  const formView =
    view === "provider-key" || (view === "provider-model" && customModel) || view === "mcp-edit";

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
          className="dc-composer-menu-body flex max-h-[min(50vh,22rem)] flex-col overflow-y-auto py-0.5"
        >
          {view === "provider-key" ? (
            <Label className="flex flex-col items-stretch gap-1 px-3 py-1.5" htmlFor={keyFormId}>
              <span className="text-muted-foreground text-xs">Paste API key, then Enter</span>
              <Input
                ref={keyInputRef}
                id={keyFormId}
                type="password"
                value={keyDraft}
                placeholder={providerKeyPlaceholder(providerPick)}
                autoComplete="off"
                spellCheck={false}
                aria-invalid={Boolean(providerError)}
                className="border-border bg-transparent w-full rounded-none border px-2 py-1.5 font-mono text-sm outline-none h-auto"
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
              <span className="text-muted-foreground text-xs">Model slug, then Enter</span>
              <Input
                ref={customModelRef}
                type="text"
                value={modelDraft}
                autoComplete="off"
                spellCheck={false}
                className="border-border bg-transparent w-full rounded-none border px-2 py-1.5 font-mono text-sm outline-none h-auto"
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
              <pre className="border-border text-muted-foreground max-h-32 overflow-auto border px-2 py-1.5 font-mono text-[11px] leading-4">
                {mcpConfigJson(mcpDraft)}
              </pre>
              <div className="flex flex-col items-stretch gap-1">
                <span className="text-muted-foreground text-xs" id="mcp-id-label">
                  id
                </span>
                <div className="relative z-10" data-mcp-id-field>
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
                    className="border-border bg-transparent w-full rounded-none border px-2 py-1 font-mono text-sm outline-none disabled:opacity-60 h-auto"
                    onFocus={() => {
                      if (mcpDraft.source === "session") setMcpIdDropdownOpen(true);
                    }}
                    onBlur={(e) => {
                      const root = e.currentTarget.closest("[data-mcp-id-field]");
                      if (e.relatedTarget instanceof Node && root?.contains(e.relatedTarget))
                        return;
                      closeMcpIdDropdown();
                    }}
                    onChange={(e) => {
                      setMcpSuggestIndex(-1);
                      if (mcpDraft.source === "session") setMcpIdDropdownOpen(true);
                      commitMcpDraft(applyWellKnownMcp(mcpDraft, e.target.value));
                    }}
                    onKeyDown={(e) => {
                      if (mcpDraft.source === "operator") return;
                      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                        if (!mcpSuggestions.length) return;
                        e.preventDefault();
                        e.stopPropagation();
                        if (!mcpIdDropdownOpen) {
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
                  {mcpIdListOpen ? (
                    <div
                      id="mcp-id-suggestions"
                      role="listbox"
                      aria-labelledby="mcp-id-label"
                      data-mcp-id-dropdown
                      className="border-border bg-background absolute inset-x-0 top-full z-20 mt-px max-h-40 overflow-y-auto overscroll-contain rounded-none border"
                      onMouseDown={(e) => e.preventDefault()}
                    >
                      {mcpSuggestionGroups.map((g) => (
                        <div key={g.group}>
                          <div className="text-muted-foreground px-3 py-1 text-xs">{g.group}</div>
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
                                className={`${MCP_SUGGEST_ROW_CLASS} ${
                                  highlighted ? "bg-muted/50" : ""
                                }`}
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
                                <span className="min-w-0 shrink-0 font-medium">{row.id}</span>
                                <span className="text-muted-foreground min-w-0 truncate text-right text-xs">
                                  {wellKnownMcpHost(row.url) || row.auth}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
              <Label className="flex flex-col items-stretch gap-1">
                <span className="text-muted-foreground text-xs">label</span>
                <Input
                  type="text"
                  value={mcpDraft.label}
                  autoComplete="off"
                  spellCheck={false}
                  className="border-border bg-transparent w-full rounded-none border px-2 py-1 font-mono text-sm outline-none h-auto"
                  onChange={(e) => commitMcpDraft({ ...mcpDraft, label: e.target.value })}
                />
              </Label>
              {mcpDraft.source === "session" ? (
                <Label className="flex flex-col items-stretch gap-1">
                  <span className="text-muted-foreground text-xs">url</span>
                  <Input
                    type="url"
                    value={mcpDraft.url}
                    placeholder="https://…"
                    autoComplete="off"
                    spellCheck={false}
                    className="border-border bg-transparent w-full rounded-none border px-2 py-1 font-mono text-sm outline-none h-auto"
                    onChange={(e) => commitMcpDraft({ ...mcpDraft, url: e.target.value })}
                  />
                </Label>
              ) : (
                <p className="text-muted-foreground text-xs">url is operator-managed (BFF)</p>
              )}
              <div className="flex flex-col items-stretch gap-1">
                <span className="text-muted-foreground text-xs" id="mcp-auth-label">
                  auth
                </span>
                <div
                  role="radiogroup"
                  aria-labelledby="mcp-auth-label"
                  className="border-border flex border"
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
                          index > 0 ? "border-border border-l" : ""
                        } ${selected ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"}`}
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
                  <span className="text-muted-foreground text-xs">token / oauth client secret</span>
                  <div className="flex min-w-0 items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-auto shrink-0 whitespace-nowrap border-border px-2 py-1"
                      disabled={mcpOAuthBusy}
                      onClick={() => void authenticateMcp()}
                    >
                      {mcpOAuthBusy ? "Authenticating…" : "Authenticate"}
                    </Button>
                    <span className="text-muted-foreground whitespace-nowrap text-xs">or</span>
                    <Input
                      type="password"
                      value={mcpDraft.token}
                      placeholder="OAuth token"
                      autoComplete="off"
                      spellCheck={false}
                      className="border-border bg-transparent min-w-0 flex-1 rounded-none border px-2 py-1 font-mono text-sm outline-none h-auto"
                      onChange={(e) => commitMcpDraft({ ...mcpDraft, token: e.target.value })}
                    />
                  </div>
                </div>
              ) : mcpDraft.auth !== "none" ? (
                <Label className="flex flex-col items-stretch gap-1">
                  <span className="text-muted-foreground text-xs">token</span>
                  <Input
                    type="password"
                    value={mcpDraft.token}
                    placeholder="Bearer token"
                    autoComplete="off"
                    spellCheck={false}
                    className="border-border bg-transparent w-full rounded-none border px-2 py-1 font-mono text-sm outline-none h-auto"
                    onChange={(e) => commitMcpDraft({ ...mcpDraft, token: e.target.value })}
                  />
                </Label>
              ) : null}
              <div className="flex flex-col items-stretch gap-1">
                <span className="text-muted-foreground text-xs">other</span>
                {Object.entries(mcpDraft.extra).map(([key, value]) => (
                  <Label key={key} className="flex flex-col items-stretch gap-1">
                    <span className="text-muted-foreground text-xs">{key}</span>
                    <Input
                      type="text"
                      value={value}
                      autoComplete="off"
                      spellCheck={false}
                      className="border-border bg-transparent w-full rounded-none border px-2 py-1 font-mono text-sm outline-none h-auto"
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
                    className="border-border bg-transparent min-w-0 flex-1 rounded-none border px-2 py-1 font-mono text-sm outline-none h-auto"
                    onChange={(e) => setMcpFieldName(e.target.value)}
                  />
                  <Input
                    type="text"
                    value={mcpFieldValue}
                    placeholder="value"
                    autoComplete="off"
                    spellCheck={false}
                    className="border-border bg-transparent min-w-0 flex-1 rounded-none border px-2 py-1 font-mono text-sm outline-none h-auto"
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
                <p className="text-destructive text-xs" role="alert">
                  {mcpError}
                </p>
              ) : null}
            </div>
          ) : null}
          {view === "help" ? (
            <div className="flex flex-col gap-2 px-3 py-2 text-xs leading-relaxed" data-embed-help>
              <p className="text-muted-foreground">
                Ask about OCC policies, procedures and help articles, search internal notes, or
                check live support tickets.
              </p>
              <div className="flex flex-col gap-1">
                <span className="text-muted-foreground text-[11px] uppercase tracking-wide">
                  Try asking
                </span>
                <span>How do I raise a support ticket?</span>
                <span>What is our data retention policy?</span>
                <span>Summarise my open support tickets.</span>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-muted-foreground text-[11px] uppercase tracking-wide">
                  Commands
                </span>
                <span className="font-mono">
                  /models · /language · /tools · /mcp · /settings · /new
                </span>
              </div>
              <span className="text-muted-foreground">Enter sends · Shift+Enter adds a line</span>
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
            ? rows.map((row, index) => {
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
                    data-cursor={index === cursor ? "true" : undefined}
                    className={MENU_ROW_CLASS}
                    ref={(node) => {
                      if (index === cursor) node?.scrollIntoView({ block: "nearest" });
                    }}
                    onMouseEnter={() => setCursor(index)}
                    onClick={() => row.activate()}
                    onKeyDown={(e) => onRowKey(e, index)}
                  >
                    {/* The user-message chevron marks the hovered / arrow-key
                        row and pushes that row's content right to make room.
                        A checked row keeps its right-hand diamond instead: no
                        chevron, so the two marks never double up. */}
                    {index === cursor && !(exclusive && row.checked) ? (
                      <span className="aui-menu-cursor" aria-hidden>
                        <DotMatrix state="user" className="size-3.5" />
                      </span>
                    ) : null}
                    <span className="min-w-0 shrink-0 font-medium">{row.label}</span>
                    {row.value || (exclusive && row.checked) ? (
                      <span className="text-muted-foreground ml-auto flex min-w-0 items-center justify-end gap-2 truncate text-right text-xs">
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
            <p className="text-muted-foreground px-3 py-1 text-xs">Checking key…</p>
          ) : null}
          {providerError ? (
            <p className="text-destructive px-3 py-1 text-xs" role="alert">
              {providerError}
            </p>
          ) : null}
        </div>
        <MenuScrollbar targetRef={menuBodyRef} />
      </div>
      <div className="text-muted-foreground px-3 py-1 font-mono text-[0.68rem]">
        {title} · ↑↓ navigate · ⏎/→ submit · esc/← back
      </div>
    </div>
  );

  const host = composerHost();
  if (!host) return null;
  return createPortal(body, host);
}
