"use client";

import { useCallback, useState } from "react";
import {
  Alert,
  AlertDescription,
  Button,
  Input,
  Label,
  Select,
  SelectItem,
  SelectItemIndicator,
  SelectPopup,
  SelectTrigger,
  SelectValue,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@digithings/ui/ui";
import {
  PROVIDER_LABELS,
  PROVIDER_MODELS,
  type ProviderId,
  validateProviderKey,
} from "@/lib/providerSettings";

type TestResult = { ok: boolean; model?: string; error?: string } | null;

// Record over ProviderId, not a ternary chain — a provider missing from this
// map is a compile error rather than a silent fallthrough to a generic (and
// possibly wrong-format) placeholder. xai was the provider a ternary chain
// missed on this PR: it fell through to the generic "sk-…" text even though
// x.ai keys start with "xai-" (#2348).
const KEY_PLACEHOLDERS: Record<ProviderId, string> = {
  openrouter: "sk-or-v1-…",
  openai: "sk-…",
  anthropic: "sk-ant-…",
  gemini: "AI…",
  xai: "xai-…",
};

/** The panel body: note, provider picker, key field, model picker, test
 *  result, actions. Exported for the contract test — the kit `Sheet` around
 *  it portals (client-mount only), so server-render assertions run here. */
export function ProviderSettingsForm({
  storedKey,
  storedProvider,
  storedModel,
  isSet,
  onSave,
  onClear,
  onClose,
}: {
  storedKey: string;
  storedProvider: ProviderId;
  storedModel: string;
  isSet: boolean;
  onSave: (key: string, provider: ProviderId, model: string) => void;
  onClear: () => void;
  onClose: () => void;
}) {
  const [inputKey, setInputKey] = useState(storedKey);
  const [inputProvider, setInputProvider] = useState<ProviderId>(storedProvider);
  const [inputModel, setInputModel] = useState(storedModel);
  const [showKey, setShowKey] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<TestResult>(null);
  const [testing, setTesting] = useState(false);

  const handleProviderChange = useCallback(
    (p: ProviderId) => {
      setInputProvider(p);
      setInputModel(PROVIDER_MODELS[p][0]?.id ?? "");
      setTestResult(null);
      if (inputKey) setValidationError(validateProviderKey(inputKey, p));
      else setValidationError(null);
    },
    [inputKey],
  );

  const handleTest = useCallback(async () => {
    const err = validateProviderKey(inputKey, inputProvider);
    if (err) {
      setValidationError(err);
      return;
    }
    setTesting(true);
    setTestResult(null);
    try {
      const resp = await fetch("/api/byok/test", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "X-BYOK-Key": inputKey,
          "X-BYOK-Provider": inputProvider,
        },
        body: JSON.stringify({}),
      });
      setTestResult((await resp.json()) as TestResult);
    } catch {
      setTestResult({ ok: false, error: "Network error — could not reach server." });
    } finally {
      setTesting(false);
    }
  }, [inputKey, inputProvider]);

  const handleSave = useCallback(() => {
    const err = validateProviderKey(inputKey, inputProvider);
    if (err) {
      setValidationError(err);
      return;
    }
    onSave(inputKey, inputProvider, inputModel);
    onClose();
  }, [inputKey, inputProvider, inputModel, onSave, onClose]);

  const handleClear = useCallback(() => {
    onClear();
    onClose();
  }, [onClear, onClose]);

  const providers = Object.keys(PROVIDER_MODELS) as ProviderId[];
  const models = PROVIDER_MODELS[inputProvider];

  return (
    <>
      <p className="mb-4 mt-0 border border-hair bg-ink/[0.04] px-[0.6rem] py-2 text-[0.72rem] leading-[1.45] text-ink-mute">
        Your key stays in this browser only. It is sent per request to route your chat — never
        stored on our servers.
      </p>

      <div className="mb-[0.85rem]">
        <span className="mb-[0.35rem] block text-[0.68rem] uppercase tracking-[0.06em] text-ink-mute">
          Provider
        </span>
        <div className="flex flex-wrap gap-[0.35rem]" role="group" aria-label="Provider">
          {providers.map((p) => {
            const active = inputProvider === p;
            return (
              <Button
                key={p}
                type="button"
                size="xs"
                variant={active ? "secondary" : "outline"}
                aria-pressed={active}
                className={active ? "border-ink/30 text-ink" : "text-ink-soft"}
                onClick={() => handleProviderChange(p)}
              >
                {PROVIDER_LABELS[p]}
              </Button>
            );
          })}
        </div>
      </div>

      <div className="mb-[0.85rem]">
        <Label
          htmlFor="dc-byok-key"
          className="mb-[0.35rem] block text-[0.68rem] uppercase tracking-[0.06em] text-ink-mute"
        >
          API key
        </Label>
        <div className="flex items-center gap-[0.35rem]">
          <Input
            id="dc-byok-key"
            className="flex-1"
            type={showKey ? "text" : "password"}
            value={inputKey}
            onChange={(e) => {
              setInputKey(e.target.value);
              setValidationError(null);
              setTestResult(null);
            }}
            onBlur={() => {
              if (inputKey) setValidationError(validateProviderKey(inputKey, inputProvider));
            }}
            placeholder={KEY_PLACEHOLDERS[inputProvider]}
            autoComplete="off"
            spellCheck={false}
          />
          <Button
            type="button"
            size="xs"
            variant="outline"
            className="text-ink-soft"
            onClick={() => setShowKey((v) => !v)}
            aria-label={showKey ? "Hide key" : "Show key"}
          >
            {showKey ? "hide" : "show"}
          </Button>
        </div>
        {validationError ? (
          <Alert variant="destructive" className="mt-[0.35rem]">
            <AlertDescription>{validationError}</AlertDescription>
          </Alert>
        ) : null}
      </div>

      <div className="mb-[0.85rem]">
        <Label
          htmlFor="dc-byok-model"
          className="mb-[0.35rem] block text-[0.68rem] uppercase tracking-[0.06em] text-ink-mute"
        >
          Model
        </Label>
        <Select
          value={inputModel}
          onValueChange={(value) => {
            if (value != null) setInputModel(String(value));
          }}
        >
          <SelectTrigger id="dc-byok-model" className="w-full">
            <SelectValue>
              {(value) => models.find((m) => m.id === value)?.label ?? ""}
            </SelectValue>
          </SelectTrigger>
          <SelectPopup>
            {models.map((m) => (
              <SelectItem key={m.id} value={m.id}>
                {m.label}
                <SelectItemIndicator />
              </SelectItem>
            ))}
          </SelectPopup>
        </Select>
      </div>

      {testResult ? (
        <p
          role="status"
          className={
            testResult.ok
              ? "mt-[0.35rem] text-[0.72rem] text-accent"
              : "mt-[0.35rem] text-[0.72rem] text-danger"
          }
        >
          {testResult.ok
            ? `Key verified${testResult.model ? ` · ${testResult.model}` : ""}.`
            : testResult.error}
        </p>
      ) : null}

      <div className="mt-2 flex flex-wrap gap-[0.4rem]">
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="text-ink-soft"
          onClick={() => void handleTest()}
          disabled={testing || !inputKey.trim()}
        >
          {testing ? "testing…" : "test key"}
        </Button>
        <Button type="button" size="sm" onClick={handleSave}>
          {isSet ? "update" : "save"}
        </Button>
        {isSet ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="text-ink-soft"
            onClick={handleClear}
          >
            use free pool
          </Button>
        ) : null}
      </div>
    </>
  );
}

/**
 * BYOK panel — the kit `Sheet` (Base UI Dialog) replacing the hand-built
 * slide-over. Base UI owns the backdrop dismissal, Escape, focus trap +
 * focus return, and page scroll lock; `SheetContent`'s stock close button
 * replaces the old `.dc-settings-close`.
 */
export function ProviderSettings({
  open,
  onClose,
  apiKey: storedKey,
  provider: storedProvider,
  model: storedModel,
  isSet,
  onSave,
  onClear,
}: {
  open: boolean;
  onClose: () => void;
  apiKey: string;
  provider: ProviderId;
  model: string;
  isSet: boolean;
  onSave: (key: string, provider: ProviderId, model: string) => void;
  onClear: () => void;
}) {
  const formKey = `${storedKey}:${storedProvider}:${storedModel}`;

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>Bring your own key</SheetTitle>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
          <ProviderSettingsForm
            key={formKey}
            storedKey={storedKey}
            storedProvider={storedProvider}
            storedModel={storedModel}
            isSet={isSet}
            onSave={onSave}
            onClear={onClear}
            onClose={onClose}
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}
