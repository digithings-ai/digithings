"use client";

import { useCallback, useEffect, useState } from "react";
import { Eye, EyeOff, Key, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
} from "@/hooks/use-byok-key";

type TestResult = { ok: boolean; model?: string; error?: string } | null;

export function BYOKSettingsPanel({ inline = false }: { inline?: boolean } = {}) {
  const { key: storedKey, provider: storedProvider, isSet, setKey, clearKey } =
    useBYOKKey();

  const [open, setOpen] = useState(inline);
  const [inputKey, setInputKey] = useState("");
  const [inputProvider, setInputProvider] = useState<BYOKProvider>("openai");
  const [showKey, setShowKey] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<TestResult>(null);
  const [testing, setTesting] = useState(false);

  // Sync local form state when panel opens
  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- #257: derive via onOpenChange
      setInputKey(storedKey);
      setInputProvider(storedProvider);
      setValidationError(null);
      setTestResult(null);
      setShowKey(false);
    }
  }, [open, storedKey, storedProvider]);

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
    const err = validateBYOKKey(inputKey, inputProvider);
    if (err) {
      setValidationError(err);
      return;
    }
    setTesting(true);
    setTestResult(null);
    try {
      const resp = await fetch("/api/byok/test", {
        method: "POST",
        credentials: "include",
        headers: {
          "content-type": "application/json",
          "X-BYOK-Key": inputKey,
          "X-BYOK-Provider": inputProvider,
        },
        body: JSON.stringify({}),
      });
      const data = (await resp.json()) as TestResult;
      setTestResult(data);
    } catch {
      setTestResult({ ok: false, error: "Network error — could not reach server." });
    } finally {
      setTesting(false);
    }
  }, [inputKey, inputProvider]);

  const handleSave = useCallback(() => {
    const err = validateBYOKKey(inputKey, inputProvider);
    if (err) {
      setValidationError(err);
      return;
    }
    setKey(inputKey, inputProvider);
    setOpen(false);
  }, [inputKey, inputProvider, setKey]);

  const handleClear = useCallback(() => {
    clearKey();
    setInputKey("");
    setInputProvider("openai");
    setValidationError(null);
    setTestResult(null);
    setOpen(false);
  }, [clearKey]);

  const body = (
    <>
      <div className="mb-5 rounded-lg border border-sky-950/40 bg-sky-950/15 px-3 py-2.5 text-[12px] text-sky-200/90 leading-relaxed">
          Your key is stored in your browser only and never saved to our servers.
          It is sent directly to the BFF on each request and not logged or persisted.
        </div>

        <div className="mb-4 space-y-1.5">
          <Label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Provider
          </Label>
          <div className="flex gap-2">
            {(["openai", "anthropic"] as BYOKProvider[]).map((p) => (
              <Button
                key={p}
                type="button"
                size="sm"
                variant={inputProvider === p ? "default" : "outline"}
                className="flex-1 capitalize"
                onClick={() => handleProviderChange(p)}
              >
                {p === "openai" ? "OpenAI" : "Anthropic"}
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
                inputProvider === "openai" ? "sk-…" : "sk-ant-…"
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

        {/* Format hint */}
        <p className="mb-5 text-[11px] text-muted-foreground">
          {inputProvider === "openai"
            ? "OpenAI keys start with sk- (from platform.openai.com/api-keys)"
            : "Anthropic keys start with sk-ant- (from console.anthropic.com/settings/keys)"}
        </p>

        {/* Test result */}
        {testResult !== null && (
          <div
            className={`mb-4 rounded-lg border px-3 py-2 text-[12px] ${
              testResult.ok
                ? "border-emerald-950/40 bg-emerald-950/15 text-emerald-200"
                : "border-destructive/40 bg-destructive/10 text-destructive-foreground"
            }`}
          >
            {testResult.ok
              ? `Connected${testResult.model ? ` — model: ${testResult.model}` : ""}`
              : `Error: ${testResult.error ?? "Unknown error"}`}
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-col gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={testing || !inputKey}
            onClick={() => void handleTest()}
          >
            {testing ? (
              <Loader2 className="mr-2 size-4 animate-spin" />
            ) : null}
            Test connection
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={!inputKey}
            onClick={handleSave}
          >
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

  if (inline) {
    return (
      <div className="max-w-lg">
        <h3 className="mb-4 flex items-center gap-2 text-base font-semibold">
          <Key className="size-4" />
          Bring Your Own Key
        </h3>
        {body}
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
          <span className="ml-0.5 size-2 rounded-full bg-emerald-400" aria-hidden />
        )}
      </SheetTrigger>
      <SheetContent side="right" className="w-full max-w-md">
        <SheetHeader className="mb-6">
          <SheetTitle className="flex items-center gap-2 text-base font-semibold">
            <Key className="size-4" />
            Bring Your Own Key
          </SheetTitle>
        </SheetHeader>
        {body}
      </SheetContent>
    </Sheet>
  );
}
