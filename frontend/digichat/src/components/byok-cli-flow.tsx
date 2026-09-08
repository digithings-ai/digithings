"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import {
  type BYOKProvider,
  type ByokModelOption,
  BYOK_PROVIDER_LIST,
  byokModelPresets,
  byokRequiresModel,
  moveListIndex,
  validateBYOKKey,
  validateBYOKModel,
} from "@/hooks/use-byok-key";
import {
  byokActivationGate,
  pingByokKey,
  type ByokPingResult,
} from "@/lib/byok-ping";
import { p } from "@/lib/base-path";
import { cn } from "@/lib/utils";
import { SegmentedControl } from "@digithings/web";

type Step = "provider" | "key" | "model" | "validating" | "done";

const CUSTOM_MODEL = "__custom__";

/** Providers whose validation ping already returns a live `models` list and
 * whose upstream call never reads the `model` parameter (#2347) — so the
 * ping can (and should) fire as soon as the key is submitted, instead of
 * waiting for a model to be picked. OpenRouter has its own public-catalog
 * prefetch (no key needed); x.ai has no live fetch and still needs a model
 * up front — neither belongs in this list. */
const LIVE_PING_MODEL_PROVIDERS: readonly BYOKProvider[] = ["openai", "anthropic", "gemini"];

function wantsKeyStepPing(provider: BYOKProvider): boolean {
  return LIVE_PING_MODEL_PROVIDERS.includes(provider);
}

function TermLine({
  marker,
  children,
  className,
}: {
  marker: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("dc-term-row dc-term-row-assistant", className)}>
      <span className="dc-term-marker" aria-hidden>
        {marker}
      </span>
      <div className="dc-term-body">{children}</div>
    </div>
  );
}

function maskKey(key: string): string {
  const t = key.trim();
  if (t.length <= 8) return "••••";
  return `${t.slice(0, 6)}…${t.slice(-4)}`;
}

function TermOptionList({
  options,
  labels,
  highlighted,
  onHighlight,
  onSelect,
  listLabel,
  onToggleStar,
  isStarred,
}: {
  options: readonly string[];
  labels?: readonly string[];
  highlighted: number;
  onHighlight: (i: number) => void;
  onSelect: (value: string) => void;
  listLabel: string;
  onToggleStar?: (value: string) => void;
  isStarred?: (value: string) => boolean;
}) {
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    listRef.current?.focus();
  }, []);

  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-idx="${highlighted}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [highlighted]);

  const onKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLUListElement>) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        onHighlight(moveListIndex(highlighted, options.length, "down"));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        onHighlight(moveListIndex(highlighted, options.length, "up"));
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        const value = options[highlighted];
        if (value !== undefined) onSelect(value);
      }
    },
    [highlighted, onHighlight, onSelect, options],
  );

  return (
    <ul
      ref={listRef}
      role="listbox"
      aria-label={listLabel}
      tabIndex={0}
      className="dc-byok-option-list"
      onKeyDown={onKeyDown}
    >
      {options.map((opt, i) => {
        const active = i === highlighted;
        return (
          <li key={opt || "(default)"} role="option" aria-selected={active} data-idx={i}>
            {onToggleStar && opt !== CUSTOM_MODEL ? (
              <button
                type="button"
                className="dc-byok-star"
                aria-label={isStarred?.(opt) ? "remove from custom" : "add to custom"}
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleStar(opt);
                }}
              >
                {isStarred?.(opt) ? "★" : "☆"}
              </button>
            ) : null}
            <button
              type="button"
              className={cn("dc-byok-option", active && "dc-byok-option-active")}
              onMouseEnter={() => onHighlight(i)}
              onClick={() => onSelect(opt)}
            >
              <span className="dc-byok-option-cursor" aria-hidden>
                {active ? "❯" : " "}
              </span>
              <span className="font-mono">{labels?.[i] ?? opt}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export type ByokCliFlowProps = {
  onClose: () => void;
  /** Called only after a successful provider ping. Parent holds session memory. */
  onActivate: (key: string, provider: BYOKProvider, model: string) => void;
  onClear?: () => void;
  /** When BYOK is already active this session (a validated key is currently
   * live). Also gates the "done" step / re-key display — a non-null `active`
   * renders "BYOK active" text, so it must never be used just to seed the
   * picker's starting selection. */
  active?: { provider: BYOKProvider; model: string } | null;
  /**
   * Non-secret provider/model choice to pre-select the picker with, when no
   * key is currently active — e.g. restored from the digichat_byok_pref
   * cookie by useBYOKKey(). Distinct from `active`: this does NOT imply a
   * live/validated key, so it only seeds the initial provider/model state
   * and never flips the initial step to "done".
   */
  initialProvider?: BYOKProvider;
  initialModel?: string;
  title?: string;
  className?: string;
};

export function ByokCliFlow({
  onClose,
  onActivate,
  onClear,
  active = null,
  initialProvider,
  initialModel,
  title,
  className,
}: ByokCliFlowProps) {
  const [step, setStep] = useState<Step>(active ? "done" : "provider");
  const [provider, setProvider] = useState<BYOKProvider>(
    active?.provider ?? initialProvider ?? "openrouter",
  );
  const [providerHi, setProviderHi] = useState(() =>
    Math.max(
      0,
      BYOK_PROVIDER_LIST.indexOf(active?.provider ?? initialProvider ?? "openrouter"),
    ),
  );
  const [inputKey, setInputKey] = useState("");
  const [model, setModel] = useState(active?.model ?? initialModel ?? "");
  const [modelHi, setModelHi] = useState(0);
  const [customModel, setCustomModel] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ping, setPing] = useState<ByokPingResult | null>(null);
  /** Result of the OpenAI/Anthropic/Gemini key-step ping (see
   * LIVE_PING_MODEL_PROVIDERS). Cached here so model selection can reuse it
   * instead of pinging a second time — the single-round-trip contract in
   * #2347. Reset on provider change / clear / restart, same as `ping`. */
  const [keyPing, setKeyPing] = useState<ByokPingResult | null>(null);
  const [keyPingPending, setKeyPingPending] = useState(false);
  type LiveBuckets = {
    free: ByokModelOption[];
    opensource: ByokModelOption[];
    flagship: ByokModelOption[];
    all: ByokModelOption[];
  };
  const [liveModels, setLiveModels] = useState<LiveBuckets | null>(null);
  const [modelsFetchFailed, setModelsFetchFailed] = useState(false);
  const [tier, setTier] = useState<"free" | "opensource" | "flagship" | "all" | "custom">("all");
  const [customIds, setCustomIds] = useState<Set<string>>(new Set());
  const keyInputRef = useRef<HTMLInputElement>(null);
  const customModelRef = useRef<HTMLInputElement>(null);
  const formId = useId();
  /** Drop in-flight ping activation if the flow unmounts (Escape / cancel). */
  const aliveRef = useRef(true);

  const tieredOptions = provider === "openrouter" && liveModels ? liveModels : null;
  const liveKeyStepModels: ByokModelOption[] | null =
    wantsKeyStepPing(provider) && keyPing?.ok && keyPing.models && keyPing.models.length > 0
      ? keyPing.models.map((m) => ({ id: m.id, label: m.label }))
      : null;

  const toggleCustom = useCallback((id: string) => {
    setCustomIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const modelOptions = (() => {
    if (tieredOptions) {
      const list =
        tier === "custom"
          ? tieredOptions.all.filter((m) => customIds.has(m.id))
          : tieredOptions[tier];
      return [...list.map((m) => m.id), CUSTOM_MODEL];
    }
    if (liveKeyStepModels) {
      const liveIds = liveKeyStepModels.map((m) => m.id);
      return byokRequiresModel(provider)
        ? [...liveIds, CUSTOM_MODEL]
        : ["", ...liveIds, CUSTOM_MODEL];
    }
    const presets = [...byokModelPresets(provider)];
    if (!byokRequiresModel(provider)) {
      return ["", ...presets, CUSTOM_MODEL];
    }
    return [...presets, CUSTOM_MODEL];
  })();

  const modelLabels = modelOptions.map((m) => {
    if (m === "") return "(provider default)";
    if (m === CUSTOM_MODEL) return "custom…";
    if (tieredOptions) {
      return tieredOptions.all.find((o) => o.id === m)?.label ?? m;
    }
    if (liveKeyStepModels) {
      return liveKeyStepModels.find((o) => o.id === m)?.label ?? m;
    }
    return m;
  });

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (provider !== "openrouter" || liveModels || modelsFetchFailed) return;
    let cancelled = false;
    fetch(p("/api/byok/models?provider=openrouter"), { credentials: "include" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: LiveBuckets & { ok: boolean }) => {
        if (cancelled) return;
        setLiveModels({ free: data.free, opensource: data.opensource, flagship: data.flagship, all: data.all });
      })
      .catch(() => {
        if (!cancelled) setModelsFetchFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [provider, liveModels, modelsFetchFailed]);

  useEffect(() => {
    if (step === "key") keyInputRef.current?.focus();
    if (step === "model" && customModel) customModelRef.current?.focus();
  }, [step, customModel]);

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (step === "key") {
        setStep("provider");
        return;
      }
      if (step === "model" && customModel) {
        setCustomModel(false);
        return;
      }
      if (step === "model") {
        setStep("key");
        return;
      }
      onClose();
    };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [step, customModel, onClose]);

  const selectProvider = useCallback((p: string) => {
    const next = p as BYOKProvider;
    setProvider(next);
    setModel("");
    setCustomModel(false);
    setModelHi(0);
    setError(null);
    setPing(null);
    setKeyPing(null);
    setKeyPingPending(false);
    setCustomIds(new Set());
    setStep("key");
  }, []);

  const submitKey = useCallback(() => {
    const err = validateBYOKKey(inputKey, provider);
    if (err) {
      setError(err);
      return;
    }
    setError(null);
    setStep("model");
    if (wantsKeyStepPing(provider)) {
      setKeyPing(null);
      setKeyPingPending(true);
      void pingByokKey(inputKey, provider, "", { requireModel: false }).then((result) => {
        if (!aliveRef.current) return;
        setKeyPingPending(false);
        setKeyPing(result);
      });
    }
  }, [inputKey, provider]);

  const runValidateAndActivate = useCallback(
    async (chosenModel: string) => {
      const gateFormat = validateBYOKKey(inputKey, provider);
      if (gateFormat) {
        setError(gateFormat);
        setStep("key");
        return;
      }
      // Single-round-trip contract (#2347): if the key-step ping already
      // succeeded for this provider, reuse it directly instead of pinging
      // /api/byok/test a second time for model selection.
      if (wantsKeyStepPing(provider) && keyPing?.ok) {
        const modelFormatErr = validateBYOKModel(chosenModel, provider);
        if (modelFormatErr) {
          setError(modelFormatErr);
          return;
        }
        setError(null);
        setPing(keyPing);
        onActivate(inputKey.trim(), provider, chosenModel.trim());
        setStep("done");
        return;
      }
      setError(null);
      setPing(null);
      setStep("validating");
      const result = await pingByokKey(inputKey, provider, chosenModel);
      if (!aliveRef.current) return;
      setPing(result);
      const refuse = byokActivationGate(result);
      if (refuse) {
        setError(refuse);
        setStep("model");
        return;
      }
      onActivate(inputKey.trim(), provider, chosenModel.trim());
      setStep("done");
    },
    [inputKey, provider, onActivate, keyPing],
  );

  const selectModel = useCallback(
    (value: string) => {
      if (value === CUSTOM_MODEL) {
        setCustomModel(true);
        setModel("");
        return;
      }
      setCustomModel(false);
      setModel(value);
      void runValidateAndActivate(value);
    },
    [runValidateAndActivate],
  );

  const submitCustomModel = useCallback(() => {
    if (byokRequiresModel(provider) && !model.trim()) {
      setError(`Model is required for ${provider}.`);
      return;
    }
    void runValidateAndActivate(model.trim());
  }, [model, provider, runValidateAndActivate]);

  const handleClear = useCallback(() => {
    onClear?.();
    setInputKey("");
    setModel("");
    setPing(null);
    setKeyPing(null);
    setKeyPingPending(false);
    setError(null);
    setCustomModel(false);
    setCustomIds(new Set());
    setStep("provider");
  }, [onClear]);

  const restart = useCallback(() => {
    setInputKey("");
    setModel("");
    setPing(null);
    setKeyPing(null);
    setKeyPingPending(false);
    setError(null);
    setCustomModel(false);
    setCustomIds(new Set());
    setStep("provider");
  }, []);

  const configuring =
    step === "provider" || step === "key" || step === "model" || step === "validating";

  return (
    <div
      className={cn("dc-byok-flow", className)}
      role="region"
      aria-label={title ?? "Bring your own API key"}
    >
      <TermLine marker="▸">
        <span style={{ color: "var(--text-secondary)" }}>
          <code className="font-mono">{title ?? "byok configure"}</code>
          {" — "}
          key stays in session memory only. Refresh clears it. Sent per-request
          as X-BYOK; never logged or stored server-side.
        </span>
      </TermLine>

      {(active || step === "done") && !configuring ? (
        <TermLine marker="·">
          <span
            className="font-mono text-[12px]"
            style={{ color: "var(--text-secondary)" }}
          >
            active: {active?.provider ?? provider}
            {(active?.model ?? model) ? ` · ${active?.model ?? model}` : ""} ·
            session only
          </span>
        </TermLine>
      ) : null}

      {configuring ? (
        <>
          {step !== "provider" ? (
            <TermLine marker="·">
              <span className="font-mono text-[12px]" style={{ color: "var(--text-secondary)" }}>
                provider: {provider}
              </span>
            </TermLine>
          ) : null}

          {provider === "openrouter" && !liveModels && !modelsFetchFailed ? (
            <TermLine marker="·">
              <span className="font-mono text-[12px]" style={{ color: "var(--text-secondary)" }}>
                fetching live model catalog…
              </span>
            </TermLine>
          ) : null}

          {wantsKeyStepPing(provider) && keyPingPending ? (
            <TermLine marker="·">
              <span className="font-mono text-[12px]" style={{ color: "var(--text-secondary)" }}>
                fetching live model list…
              </span>
            </TermLine>
          ) : null}

          {step === "provider" ? (
            <TermLine marker=">">
              <p className="dc-byok-prompt">Select provider (↑↓ + Enter, or click)</p>
              <TermOptionList
                options={BYOK_PROVIDER_LIST}
                highlighted={providerHi}
                onHighlight={setProviderHi}
                onSelect={selectProvider}
                listLabel="BYOK providers"
              />
            </TermLine>
          ) : null}

          {step === "key" ? (
            <TermLine marker=">">
              <label htmlFor={`${formId}-key`} className="dc-byok-prompt">
                Paste API key, then Enter
              </label>
              <input
                ref={keyInputRef}
                id={`${formId}-key`}
                type="password"
                value={inputKey}
                onChange={(e) => {
                  setInputKey(e.target.value);
                  setError(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    submitKey();
                  }
                }}
                placeholder={
                  provider === "openai"
                    ? "sk-…"
                    : provider === "anthropic"
                      ? "sk-ant-…"
                      : provider === "gemini"
                        ? "AIza…"
                        : provider === "xai"
                          ? "xai-…"
                          : "sk-or-v1-…"
                }
                autoComplete="off"
                spellCheck={false}
                className="dc-byok-input"
                aria-invalid={!!error}
              />
            </TermLine>
          ) : null}

          {(step === "model" || step === "validating") && inputKey ? (
            <TermLine marker="·">
              <span className="font-mono text-[12px]" style={{ color: "var(--text-secondary)" }}>
                key: {maskKey(inputKey)}
              </span>
            </TermLine>
          ) : null}

          {step === "model" ? (
            <TermLine marker=">">
              <p className="dc-byok-prompt">
                {customModel
                  ? "Enter model slug, then Enter"
                  : "Select model (↑↓ + Enter, or click)"}
              </p>
              {customModel ? (
                <input
                  ref={customModelRef}
                  type="text"
                  value={model}
                  onChange={(e) => {
                    setModel(e.target.value);
                    setError(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      submitCustomModel();
                    }
                  }}
                  placeholder={byokModelPresets(provider)[0]}
                  autoComplete="off"
                  spellCheck={false}
                  className="dc-byok-input"
                />
              ) : null}
              {tieredOptions ? (
                <SegmentedControl
                  aria-label="Model tier"
                  value={tier}
                  onChange={(t) => {
                    setTier(t);
                    setModelHi(0);
                  }}
                  options={(["free", "opensource", "flagship", "all", "custom"] as const).map(
                    (t) => ({
                      value: t,
                      label: `${t} (${t === "custom" ? customIds.size : tieredOptions[t].length})`,
                    }),
                  )}
                />
              ) : null}
              {!customModel ? (
                <TermOptionList
                  options={modelOptions}
                  labels={modelLabels}
                  highlighted={modelHi}
                  onHighlight={setModelHi}
                  onSelect={selectModel}
                  listLabel="BYOK models"
                  onToggleStar={tieredOptions ? toggleCustom : undefined}
                  isStarred={tieredOptions ? (id) => customIds.has(id) : undefined}
                />
              ) : null}
            </TermLine>
          ) : null}

          {step === "validating" ? (
            <TermLine marker="·">
              <span className="font-mono text-[12px]" style={{ color: "var(--accent)" }}>
                ping {provider}
                {model ? ` · ${model}` : ""}…
              </span>
            </TermLine>
          ) : null}
        </>
      ) : null}

      {step === "done" && ping?.ok ? (
        <TermLine marker="✓">
          <span className="font-mono text-[12px]" style={{ color: "var(--accent)" }}>
            ok — BYOK active for this session
            {ping.model ? ` (${ping.model})` : ""}
          </span>
        </TermLine>
      ) : null}

      {error ? (
        <TermLine marker="✗">
          <span className="font-mono text-[12px]" style={{ color: "var(--down, #e0654b)" }}>
            {error}
          </span>
        </TermLine>
      ) : null}

      <TermLine marker="·">
        <div className="dc-byok-actions">
          {step === "done" || (active && !configuring) ? (
            <>
              <button type="button" className="dc-byok-action" onClick={restart}>
                reconfigure
              </button>
              {onClear ? (
                <button
                  type="button"
                  className="dc-byok-action dc-byok-action-danger"
                  onClick={handleClear}
                >
                  remove
                </button>
              ) : null}
            </>
          ) : null}
          <button type="button" className="dc-byok-action" onClick={onClose}>
            {step === "done" || active ? "close" : "cancel"} · esc
          </button>
        </div>
      </TermLine>
    </div>
  );
}
