"use client";

/**
 * Session menu docked above the composer (#3736 UI pass). Same chrome as the
 * slash palette: opaque, composer-width, command/label left, value right.
 * Arrow keys move; Enter toggles or opens a nested list; Escape closes.
 * Left/Right on `/language` cycles the full ISO list.
 */

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { createPortal } from "react-dom";
import { nextPaletteIndex } from "@digithings/digichat-ui";
import { useEmbedChatPrefs } from "@/components/stock/embed-chat-prefs";
import {
  connectedMcpConfigs,
  connectedToolIsOn,
  connectedTools,
  cycleMcpAuth,
  emptyMcpConfig,
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
  CUSTOM_PROVIDER_MODEL,
  PROVIDER_MENU_ORDER,
  defaultProviderPick,
  providerDisplayName,
  providerKeyPlaceholder,
  providerModelChoices,
  tryResolveProviderInput,
  wantsProviderKeyPing,
} from "@/components/stock/embed-provider-flow";
import { listenMcpOAuthResult, startMcpOAuth } from "@/components/stock/embed-mcp-oauth";

export type ComposerMenuKind =
  | "settings"
  | "models"
  | "mcp"
  | "tools"
  | "language"
  | "effort"
  | "provider";

type MenuView =
  | "main"
  | "language"
  | "models"
  | "effort"
  | "tools"
  | "mcp"
  | "mcp-edit"
  | "provider"
  | "provider-key"
  | "provider-model";

type MenuRow = {
  id: string;
  label: string;
  value: string;
  activate: () => void;
  checked?: boolean;
};

const EFFORTS = ["low", "medium", "high"] as const;

function slashName(id: string): string {
  return id.startsWith("/") ? id : `/${id}`;
}

function cycle<T extends string>(values: readonly T[], current: string, delta: number): T {
  const i = Math.max(0, values.indexOf(current as T));
  return values[nextPaletteIndex(i, delta, values.length)]!;
}

function initialView(kind: ComposerMenuKind): MenuView {
  if (kind === "models") return "models";
  if (kind === "language") return "language";
  if (kind === "effort") return "effort";
  if (kind === "tools") return "tools";
  if (kind === "mcp") return "mcp";
  if (kind === "provider") return "provider";
  return "main";
}

function composerHost(): HTMLElement | null {
  return document.querySelector<HTMLElement>(
    '[data-thread-skin="digichat"] .aui-composer-root',
  );
}

export function EmbedComposerMenu({
  kind,
  models,
  onClose,
  onActivateProvider,
  onClearProvider,
  providerActive,
  initialProvider,
  providerSeed,
  mcpSeed,
}: {
  kind: ComposerMenuKind;
  models?: readonly string[];
  onClose: () => void;
  onActivateProvider?: (key: string, provider: BYOKProvider, model: string) => void;
  onClearProvider?: () => void;
  providerActive?: { provider: BYOKProvider; model: string } | null;
  initialProvider?: BYOKProvider;
  providerSeed?: string;
  mcpSeed?: string;
}) {
  const api = useEmbedChatPrefs();
  const available = models ?? [];
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
  const [host, setHost] = useState<HTMLElement | null>(null);
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
  const keyInputRef = useRef<HTMLInputElement>(null);
  const customModelRef = useRef<HTMLInputElement>(null);
  const aliveRef = useRef(true);
  const mcpDraftRef = useRef(mcpDraft);
  mcpDraftRef.current = mcpDraft;
  const keyFormId = useId();

  useLayoutEffect(() => {
    setHost(composerHost());
  }, []);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  useEffect(() => {
    const next = initialView(kind);
    const providerSeeded = kind === "provider" ? tryResolveProviderInput(providerSeed ?? "") : undefined;
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
        { ...emptyMcpConfig(), id: mcpOpened, label: mcpOpened };
      setMcpDraft(hit);
      setView("mcp-edit");
      setCursor(0);
    } else {
      setView(next);
      if (kind === "language") {
        setCursor(Math.max(0, languageCodes.indexOf(api.prefs.language)));
      } else if (kind === "effort") {
        setCursor(Math.max(0, EFFORTS.indexOf(api.prefs.effort as (typeof EFFORTS)[number])));
      } else if (kind === "provider") {
        const current = defaultProviderPick(providerActive?.provider, initialProvider);
        setProviderPick(current);
        setCursor(Math.max(0, PROVIDER_MENU_ORDER.indexOf(current)));
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
    // Only when the opened pane changes — cycling language must not reset the cursor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, providerSeed, mcpSeed]);

  const mainRows = useMemo((): MenuRow[] => {
    const rows: MenuRow[] = [];
    rows.push({
      id: "tools",
      label: slashName("tools"),
      value: toolsMenuSummary(toolRows, (id) => connectedToolIsOn(id, toolOnInput)),
      activate: () => {
        setCursor(0);
        setView("tools");
      },
    });
    rows.push({
      id: "mcp",
      label: slashName("mcp"),
      value: mcpMenuSummaryFromConfigs(mcpConfigs, api.extraToolOn),
      activate: () => {
        setCursor(0);
        setView("mcp");
      },
    });
    rows.push({
      id: "thinking",
      label: slashName("thinking"),
      value: api.prefs.thinking ? "On" : "Off",
      checked: api.prefs.thinking,
      activate: () => api.setThinking(!api.prefs.thinking),
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
    if (onActivateProvider) {
      rows.push({
        id: "provider",
        label: slashName("provider"),
        value: providerActive
          ? providerDisplayName(providerActive.provider)
          : "Off",
        checked: Boolean(providerActive),
        activate: () => {
          const current = defaultProviderPick(providerActive?.provider, initialProvider);
          setProviderPick(current);
          setCursor(Math.max(0, PROVIDER_MENU_ORDER.indexOf(current)));
          setView("provider");
        },
      });
    }
    return rows;
  }, [api, toolRows, toolOnInput, mcpConfigs, available, onActivateProvider, languageCodes, providerActive, initialProvider]);

  const languageRows = useMemo(
    (): MenuRow[] =>
      languages.map((o) => {
        const selected = api.prefs.language === o.value;
        const native = o.native !== o.label ? o.native : "";
        return {
          id: o.value,
          label: `${o.value}  ${o.label}`,
          value: [native, selected ? "On" : ""].filter(Boolean).join(" · "),
          checked: selected,
          activate: () => {
            api.setLanguage(o.value);
          },
        };
      }),
    [languages, api],
  );

  const modelRows = useMemo((): MenuRow[] => {
    if (!available.length) {
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
    return available.map((id) => ({
      id,
      label: id,
      value: api.prefs.model === id ? "On" : "",
      checked: api.prefs.model === id,
      activate: () => {
        api.setModel(id);
      },
    }));
  }, [available, api]);

  const effortRows = useMemo(
    (): MenuRow[] =>
      EFFORTS.map((id) => ({
        id,
        label: slashName(`effort ${id}`),
        value: api.prefs.effort === id ? "On" : "",
        checked: api.prefs.effort === id,
        activate: () => {
          api.setEffort(id);
        },
      })),
    [api],
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
    return toolRows.map((t) => {
      const on = connectedToolIsOn(t.id, toolOnInput);
      return {
        id: t.id,
        label: slashName(t.slash),
        value: on ? "On" : "Off",
        checked: on,
        activate: () => toggleTool(t.id),
      };
    });
  }, [kind, onClose, toggleTool, toolOnInput, toolRows]);

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
          setView("mcp-edit");
        },
      };
    });
    rows.push({
      id: "mcp-new",
      label: slashName("mcp new"),
      value: "Add",
      activate: () => {
        setMcpDraft(emptyMcpConfig());
        setMcpError(null);
        setView("mcp-edit");
      },
    });
    return rows;
  }, [api, mcpConfigs]);

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
    const rows: MenuRow[] = PROVIDER_MENU_ORDER.map((id) => ({
      id,
      label: slashName(id),
      value: providerDisplayName(id),
      checked: providerActive?.provider === id,
      activate: () => {
        setProviderPick(id);
        setKeyDraft("");
        setModelDraft("");
        setCustomModel(false);
        setProviderError(null);
        setLiveModels(undefined);
        setView("provider-key");
      },
    }));
    if (providerActive && onClearProvider) {
      rows.push({
        id: "provider-off",
        label: slashName("provider off"),
        value: "Remove key",
        activate: () => {
          onClearProvider();
          onClose();
        },
      });
    }
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
                      : modelRows;
  const title =
    view === "language"
      ? "/language"
      : view === "models"
        ? "/models"
        : view === "effort"
          ? "/effort"
          : view === "tools"
            ? "/tools"
            : view === "mcp" || view === "mcp-edit"
              ? "/mcp"
              : view === "provider" || view === "provider-key" || view === "provider-model"
                ? "/provider"
                : "Settings";

  useEffect(() => {
    setCursor((c) => (rows.length ? Math.min(c, rows.length - 1) : 0));
  }, [rows.length]);

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
      setCursor(Math.max(0, PROVIDER_MENU_ORDER.indexOf(providerPick)));
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

  const cycleLanguage = useCallback(
    (delta: number) => {
      if (!languageCodes.length) return;
      api.setLanguage(cycle(languageCodes, api.prefs.language, delta));
    },
    [api, languageCodes],
  );

  useEffect(() => {
    if (view === "provider-key") keyInputRef.current?.focus();
    if (view === "provider-model" && customModel) customModelRef.current?.focus();
  }, [view, customModel]);

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        goBack();
        return;
      }
      const typing =
        view === "provider-key" ||
        (view === "provider-model" && customModel) ||
        view === "mcp-edit";
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
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        const row = rows[cursor];
        const delta = event.key === "ArrowRight" ? 1 : -1;
        if (view === "main" && row?.id === "language") {
          event.preventDefault();
          event.stopPropagation();
          cycleLanguage(delta);
          return;
        }
        if (view === "main" && row?.id === "effort") {
          event.preventDefault();
          event.stopPropagation();
          api.setEffort(cycle(EFFORTS, api.prefs.effort, delta));
          return;
        }
        if (
          view === "language" ||
          view === "effort" ||
          view === "models" ||
          view === "tools" ||
          view === "mcp" ||
          view === "provider" ||
          view === "provider-model"
        ) {
          event.preventDefault();
          event.stopPropagation();
          move(delta);
          return;
        }
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
    [api, cursor, customModel, cycleLanguage, goBack, languageCodes.length, move, rows, view],
  );

  useEffect(() => {
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [onKeyDown]);

  const onRowKey = (event: ReactKeyboardEvent, index: number) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      rows[index]?.activate();
    }
  };

  const body = (
    <div
      className="dc-composer-menu aui-composer-trigger-popover absolute inset-x-0 bottom-full z-50 mb-1 w-full overflow-hidden rounded-none border"
      data-thread-skin="digichat"
      data-embed-settings
      data-embed-composer-menu
      role="menu"
      aria-label={title}
    >
      <div className="text-muted-foreground flex items-center justify-between border-b px-3 py-1.5 text-xs tracking-wide uppercase">
        <span>
          {title}
          {view === "provider-key" || view === "provider-model"
            ? ` ${providerPick}`
            : view === "mcp-edit" && mcpDraft.id
              ? ` ${mcpDraft.id}`
              : view === "mcp-edit"
                ? " new"
                : ""}
        </span>
        <button
          type="button"
          className="hover:text-foreground text-xs tracking-normal normal-case underline-offset-2 hover:underline"
          onClick={goBack}
        >
          escape
        </button>
      </div>
      <div className="flex max-h-[min(50vh,22rem)] flex-col overflow-y-auto py-1">
        {view === "provider-key" ? (
          <label className="flex flex-col gap-1 px-3 py-1.5" htmlFor={keyFormId}>
            <span className="text-muted-foreground text-xs">Paste API key, then Enter</span>
            <input
              ref={keyInputRef}
              id={keyFormId}
              type="password"
              value={keyDraft}
              placeholder={providerKeyPlaceholder(providerPick)}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={Boolean(providerError)}
              className="border-border bg-transparent w-full rounded-none border px-2 py-1.5 font-mono text-sm outline-none"
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
          </label>
        ) : null}
        {view === "provider-model" && customModel ? (
          <label className="flex flex-col gap-1 px-3 py-1.5">
            <span className="text-muted-foreground text-xs">Model slug, then Enter</span>
            <input
              ref={customModelRef}
              type="text"
              value={modelDraft}
              autoComplete="off"
              spellCheck={false}
              className="border-border bg-transparent w-full rounded-none border px-2 py-1.5 font-mono text-sm outline-none"
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
          </label>
        ) : null}
        {view === "mcp-edit" ? (
          <div className="flex flex-col gap-2 px-3 py-1.5">
            <pre className="border-border text-muted-foreground max-h-32 overflow-auto border px-2 py-1.5 font-mono text-[11px] leading-4">
              {mcpConfigJson(mcpDraft)}
            </pre>
            <label className="flex flex-col gap-1">
              <span className="text-muted-foreground text-xs">id</span>
              <input
                type="text"
                value={mcpDraft.id}
                disabled={mcpDraft.source === "operator"}
                placeholder="linear"
                autoComplete="off"
                spellCheck={false}
                className="border-border bg-transparent w-full rounded-none border px-2 py-1 font-mono text-sm outline-none disabled:opacity-60"
                onChange={(e) => commitMcpDraft({ ...mcpDraft, id: e.target.value.trim().toLowerCase() })}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-muted-foreground text-xs">label</span>
              <input
                type="text"
                value={mcpDraft.label}
                autoComplete="off"
                spellCheck={false}
                className="border-border bg-transparent w-full rounded-none border px-2 py-1 font-mono text-sm outline-none"
                onChange={(e) => commitMcpDraft({ ...mcpDraft, label: e.target.value })}
              />
            </label>
            {mcpDraft.source === "session" ? (
              <label className="flex flex-col gap-1">
                <span className="text-muted-foreground text-xs">url</span>
                <input
                  type="url"
                  value={mcpDraft.url}
                  placeholder="https://…"
                  autoComplete="off"
                  spellCheck={false}
                  className="border-border bg-transparent w-full rounded-none border px-2 py-1 font-mono text-sm outline-none"
                  onChange={(e) => commitMcpDraft({ ...mcpDraft, url: e.target.value })}
                />
              </label>
            ) : (
              <p className="text-muted-foreground text-xs">url is operator-managed (BFF)</p>
            )}
            <button
              type="button"
              className="flex w-full items-baseline justify-between px-0 py-1 text-start text-sm"
              onClick={() => commitMcpDraft({ ...mcpDraft, auth: cycleMcpAuth(mcpDraft.auth, 1) })}
            >
              <span>auth</span>
              <span className="text-muted-foreground text-xs">{mcpDraft.auth}</span>
            </button>
            {mcpDraft.auth === "oauth" && !mcpDraft.token.trim() ? (
              <button
                type="button"
                className="border-border w-full border px-2 py-1.5 text-left text-sm"
                disabled={mcpOAuthBusy}
                onClick={() => void authenticateMcp()}
              >
                {mcpOAuthBusy ? "Authenticating…" : "Authenticate"}
              </button>
            ) : null}
            {mcpDraft.auth !== "none" ? (
              <label className="flex flex-col gap-1">
                <span className="text-muted-foreground text-xs">
                  {mcpDraft.auth === "oauth" ? "token / oauth client secret" : "token"}
                </span>
                <input
                  type="password"
                  value={mcpDraft.token}
                  placeholder={mcpDraft.auth === "oauth" ? "OAuth token or paste after login" : "Bearer token"}
                  autoComplete="off"
                  spellCheck={false}
                  className="border-border bg-transparent w-full rounded-none border px-2 py-1 font-mono text-sm outline-none"
                  onChange={(e) => commitMcpDraft({ ...mcpDraft, token: e.target.value })}
                />
              </label>
            ) : null}
            {Object.entries(mcpDraft.extra).map(([key, value]) => (
              <label key={key} className="flex flex-col gap-1">
                <span className="text-muted-foreground text-xs">{key}</span>
                <input
                  type="text"
                  value={value}
                  autoComplete="off"
                  spellCheck={false}
                  className="border-border bg-transparent w-full rounded-none border px-2 py-1 font-mono text-sm outline-none"
                  onChange={(e) =>
                    commitMcpDraft({
                      ...mcpDraft,
                      extra: { ...mcpDraft.extra, [key]: e.target.value },
                    })
                  }
                />
              </label>
            ))}
            <div className="flex gap-2">
              <input
                type="text"
                value={mcpFieldName}
                placeholder="field"
                autoComplete="off"
                spellCheck={false}
                className="border-border bg-transparent min-w-0 flex-1 rounded-none border px-2 py-1 font-mono text-sm outline-none"
                onChange={(e) => setMcpFieldName(e.target.value)}
              />
              <input
                type="text"
                value={mcpFieldValue}
                placeholder="value"
                autoComplete="off"
                spellCheck={false}
                className="border-border bg-transparent min-w-0 flex-1 rounded-none border px-2 py-1 font-mono text-sm outline-none"
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
            <p className="text-muted-foreground text-xs">Enter on value adds the field to the JSON.</p>
            {mcpDraft.source === "session" && mcpDraft.id ? (
              <button
                type="button"
                className="text-destructive text-left text-xs"
                onClick={() => {
                  api.removeMcpConfig(mcpDraft.id);
                  setView("mcp");
                }}
              >
                Remove this session MCP
              </button>
            ) : null}
            {mcpError ? (
              <p className="text-destructive text-xs" role="alert">
                {mcpError}
              </p>
            ) : null}
          </div>
        ) : null}
        {view !== "provider-key" &&
        !(view === "provider-model" && customModel) &&
        view !== "mcp-edit"
          ? rows.map((row, index) => {
              const toggle = typeof row.checked === "boolean" && (view === "main" || view === "tools");
              return (
                <button
                  key={row.id}
                  id={`dc-menu-${row.id}`}
                  type="button"
                  role={toggle ? "menuitemcheckbox" : "menuitem"}
                  aria-checked={typeof row.checked === "boolean" ? row.checked : undefined}
                  data-cursor={index === cursor ? "true" : undefined}
                  className="flex w-full cursor-pointer items-baseline justify-between gap-4 px-3 py-1.5 text-start text-sm outline-none outline-offset-[-1px]"
                  ref={(node) => {
                    if (index === cursor) node?.scrollIntoView({ block: "nearest" });
                  }}
                  onMouseEnter={() => setCursor(index)}
                  onClick={() => row.activate()}
                  onKeyDown={(e) => onRowKey(e, index)}
                >
                  <span className="min-w-0 shrink-0 font-medium">{row.label}</span>
                  {row.value ? (
                    <span className="text-muted-foreground min-w-0 truncate text-right text-xs">
                      {row.value}
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
        {view === "mcp" ? (
          <p className="text-muted-foreground px-3 py-1 text-xs">
            Enter opens JSON and fields. Toggle on/off with /tools. /mcp new adds a session MCP.
            Operator URLs stay on the BFF.
          </p>
        ) : null}
        {view === "tools" ? (
          <p className="text-muted-foreground px-3 py-1 text-xs">
            Every connected tool is also a slash command. MCP JSON and auth live under /mcp.
          </p>
        ) : null}
      </div>
    </div>
  );

  if (!host) return null;
  return createPortal(body, host);
}
