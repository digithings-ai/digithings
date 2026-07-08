"use client";

import { useCallback, useState } from "react";
import { Eye, EyeOff, Key, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { p } from "@/lib/base-path";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  type BYOKProvider,
  useBYOKKey,
  validateBYOKKey,
  validateBYOKModel,
} from "@/hooks/use-byok-key";

type TestResult = { ok: boolean; model?: string; error?: string } | null;

function ByokSettingsForm({
  storedKey,
  storedProvider,
  storedModel,
  isSet,
  setKey,
  clearKey,
  onClose,
}: {
  storedKey: string;
  storedProvider: BYOKProvider;
  storedModel: string;
  isSet: boolean;
  setKey: (key: string, provider: BYOKProvider, model?: string) => void;
  clearKey: () => void;
  onClose?: () => void;
}) {
  const [inputKey, setInputKey] = useState(storedKey);
  const [inputProvider, setInputProvider] = useState<BYOKProvider>(storedProvider);
  const [inputModel, setInputModel] = useState(storedModel);
  const [showKey, setShowKey] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<TestResult>(null);
  const [testing, setTesting] = useState(false);

  const handleBlur = useCallback(() => {
    if (inputKey) {
      setValidationError(validateBYOKKey(inputKey, inputProvider));
    } else {
      setValidationError(null);
    }
  }, [inputKey, inputProvider]);

  const handleProviderChange = useCallback(
    (p: BYOKProvider) => {
      setInputProvider(p);
      if (inputKey) {
        setValidationError(validateBYOKKey(inputKey, p));
      }
      setTestResult(null);
    },
    [inputKey]
  );

  const handleTest = useCallback(async () => {
    const err = validateBYOKKey(inputKey, inputProvider) ?? validateBYOKModel(inputModel, inputProvider);
    if (err) {
      setValidationError(err);
      return;
    }
    setTesting(true);
    setTestResult(null);
    try {
      const headers: Record<string, string> = {
        "content-type": "application/json",
        "X-BYOK-Key": inputKey,
        "X-BYOK-Provider": inputProvider,
      };
      if (inputProvider === "openrouter") {
        headers["X-BYOK-Model"] = inputModel.trim();
      }
      const resp = await fetch(p("/api/byok/test"), {
        method: "POST",
        credentials: "include",
        headers,
        body: JSON.stringify({}),
      });
      const data = (await resp.json()) as TestResult;
      setTestResult(data);
    } catch {
      setTestResult({ ok: false, error: "Network error — could not reach server." });
    } finally {
      setTesting(false);
    }
  }, [inputKey, inputProvider, inputModel]);

  const handleSave = useCallback(() => {
    const err = validateBYOKKey(inputKey, inputProvider) ?? validateBYOKModel(inputModel, inputProvider);
    if (err) {
      setValidationError(err);
      return;
    }
    setKey(inputKey, inputProvider, inputModel.trim());
    onClose?.();
  }, [inputKey, inputProvider, inputModel, setKey, onClose]);

  const handleClear = useCallback(() => {
    clearKey();
    onClose?.();
  }, [clearKey, onClose]);

  return (
    <>
      <div className="mb-5 rounded-lg border border-hair bg-surface-2 px-3 py-2.5 text-[12px] text-ink-soft leading-relaxed">
        Your key is stored in your browser only and never saved to our servers.
        It is sent directly to the BFF on each request and not logged or persisted.
      </div>

      <div className="mb-4 space-y-1.5">
        <Label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Provider
        </Label>
        <div className="flex gap-2">
          {(["openrouter", "openai", "anthropic"] as BYOKProvider[]).map((p) => (
            <Button
              key={p}
              type="button"
              size="sm"
              variant={inputProvider === p ? "default" : "outline"}
              className="flex-1 capitalize"
              onClick={() => handleProviderChange(p)}
            >
              {p === "openai" ? "OpenAI" : p === "anthropic" ? "Anthropic" : "OpenRouter"}
            </Button>
          ))}
        </div>
      </div>

      <div className="mb-1 space-y-1.5">
        <Label htmlFor="byok-key-input" className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          API Key
        </Label>
        <div className="relative flex items-center">
          <Input
            id="byok-key-input"
            type={showKey ? "text" : "password"}
            value={inputKey}
            onChange={(e) => {
              setInputKey(e.target.value);
              setValidationError(null);
              setTestResult(null);
            }}
            onBlur={handleBlur}
            placeholder={
              inputProvider === "openai"
                ? "sk-…"
                : inputProvider === "anthropic"
                  ? "sk-ant-…"
                  : "sk-or-v1-…"
            }
            autoComplete="off"
            spellCheck={false}
            className="pr-9 font-mono text-sm"
            aria-describedby={validationError ? "byok-error" : undefined}
            aria-invalid={!!validationError}
          />
          <button
            type="button"
            className="absolute right-2.5 text-muted-foreground hover:text-foreground"
            onClick={() => setShowKey((v) => !v)}
            aria-label={showKey ? "Hide key" : "Show key"}
            tabIndex={-1}
          >
            {showKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        </div>
        {validationError && (
          <p id="byok-error" className="text-[11px] text-destructive">
            {validationError}
          </p>
        )}
      </div>

      <p className="mb-5 text-[11px] text-muted-foreground">
        {inputProvider === "openai"
          ? "OpenAI keys start with sk- (from platform.openai.com/api-keys)"
          : inputProvider === "anthropic"
            ? "Anthropic keys start with sk-ant- (from console.anthropic.com/settings/keys)"
            : "OpenRouter keys start with sk-or- (from openrouter.ai/keys)"}
      </p>

      {inputProvider === "openrouter" ? (
        <div className="mb-5 space-y-1.5">
          <Label htmlFor="byok-model-input" className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Model
          </Label>
          <Input
            id="byok-model-input"
            type="text"
            value={inputModel}
            onChange={(e) => {
              setInputModel(e.target.value);
              setValidationError(null);
              setTestResult(null);
            }}
            placeholder="openai/gpt-4o-mini"
            autoComplete="off"
            spellCheck={false}
            className="font-mono text-sm"
          />
        </div>
      ) : null}

      {testResult !== null && (
        <div
          className={`mb-4 rounded-lg border px-3 py-2 text-[12px] ${
            testResult.ok
              ? "border-up/40 bg-up/15 text-up"
              : "border-destructive/40 bg-destructive/10 text-destructive-foreground"
          }`}
        >
          {testResult.ok
            ? `Connected${testResult.model ? ` — model: ${testResult.model}` : ""}`
            : `Error: ${testResult.error ?? "Unknown error"}`}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={testing || !inputKey}
          onClick={() => void handleTest()}
        >
          {testing ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
          Test connection
        </Button>
        <Button type="button" size="sm" disabled={!inputKey} onClick={handleSave}>
          Save key
        </Button>
        {isSet && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-destructive hover:text-destructive"
            onClick={handleClear}
          >
            <X className="mr-1.5 size-4" />
            Remove key
          </Button>
        )}
      </div>
    </>
  );
}

export function BYOKSettingsPanel({ inline = false }: { inline?: boolean } = {}) {
  const { key: storedKey, provider: storedProvider, model: storedModel, isSet, setKey, clearKey } =
    useBYOKKey();

  const [open, setOpen] = useState(inline);
  const formKey = `${storedKey}:${storedProvider}:${storedModel}`;

  const form = (
    <ByokSettingsForm
      key={formKey}
      storedKey={storedKey}
      storedProvider={storedProvider}
      storedModel={storedModel}
      isSet={isSet}
      setKey={setKey}
      clearKey={clearKey}
      onClose={inline ? undefined : () => setOpen(false)}
    />
  );

  if (inline) {
    return (
      <div className="max-w-lg">
        <h3 className="mb-4 flex items-center gap-2 text-base font-semibold">
          <Key className="size-4" />
          Bring Your Own Key
        </h3>
        {form}
      </div>
    );
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger
        render={
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="gap-1.5 text-muted-foreground"
            aria-label={isSet ? "BYOK key configured" : "Configure your own API key"}
          />
        }
      >
        <Key className="size-4" />
        <span className="hidden sm:inline">
          {isSet ? "BYOK" : "Use my key"}
        </span>
        {isSet && (
          <span className="ml-0.5 size-2 rounded-full bg-up" aria-hidden />
        )}
      </SheetTrigger>
      <SheetContent side="right" className="w-full max-w-md">
        <SheetHeader className="mb-6">
          <SheetTitle className="flex items-center gap-2 text-base font-semibold">
            <Key className="size-4" />
            Bring Your Own Key
          </SheetTitle>
        </SheetHeader>
        {open ? form : null}
      </SheetContent>
    </Sheet>
  );
}
