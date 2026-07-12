"use client";

import { useCallback, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { p } from "@/lib/base-path";
import {
  type BYOKProvider,
  useBYOKKey,
  validateBYOKKey,
  validateBYOKModel,
} from "@/hooks/use-byok-key";
import { cn } from "@/lib/utils";

type TestResult = { ok: boolean; model?: string; error?: string } | null;

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

export function ByokCliFlow({ onClose }: { onClose: () => void }) {
  const {
    key: storedKey,
    provider: storedProvider,
    model: storedModel,
    isSet,
    setKey,
    clearKey,
  } = useBYOKKey();
  const [inputProvider, setInputProvider] = useState<BYOKProvider>(storedProvider);
  const [inputKey, setInputKey] = useState(storedKey);
  const [inputModel, setInputModel] = useState(storedModel);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<TestResult>(null);
  const [testing, setTesting] = useState(false);

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
    onClose();
  }, [inputKey, inputProvider, inputModel, setKey, onClose]);

  const handleClear = useCallback(() => {
    clearKey();
    setInputKey("");
    setInputModel("");
    setTestResult(null);
    setValidationError(null);
    onClose();
  }, [clearKey, onClose]);

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border/40 dc-term-pane">
        <TermLine marker="▸">
          <span style={{ color: "var(--text-secondary)" }}>
            <code className="font-mono">byok configure</code> — your key stays in the browser
            only. Sent per-request to the BFF; never logged or persisted server-side.
          </span>
        </TermLine>

        {isSet ? (
          <TermLine marker="·">
            <span style={{ color: "var(--text-secondary)", fontFamily: "var(--font-family-mono)", fontSize: 12 }}>
              active: {storedProvider}
              {storedProvider === "openrouter" && storedModel ? ` · ${storedModel}` : ""} · key configured
            </span>
          </TermLine>
        ) : null}

        <TermLine marker=">">
          <div className="space-y-3">
            <div>
              <p
                className="mb-2 text-[11px] uppercase tracking-wide"
                style={{ color: "var(--text-secondary)" }}
              >
                provider
              </p>
              <div className="flex gap-2">
                {(["openrouter", "openai", "anthropic"] as BYOKProvider[]).map((prov) => (
                  <button
                    key={prov}
                    type="button"
                    className={cn(
                      "dc-term-chip cursor-pointer",
                      inputProvider === prov && "ring-1 ring-[var(--accent)]",
                    )}
                    onClick={() => {
                      setInputProvider(prov);
                      setValidationError(null);
                      setTestResult(null);
                    }}
                  >
                    {prov}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label
                htmlFor="byok-cli-key"
                className="mb-2 block text-[11px] uppercase tracking-wide"
                style={{ color: "var(--text-secondary)" }}
              >
                api key
              </label>
              <input
                id="byok-cli-key"
                type="password"
                value={inputKey}
                onChange={(e) => {
                  setInputKey(e.target.value);
                  setValidationError(null);
                  setTestResult(null);
                }}
                placeholder={
                  inputProvider === "openai"
                    ? "sk-…"
                    : inputProvider === "anthropic"
                      ? "sk-ant-…"
                      : "sk-or-v1-…"
                }
                autoComplete="off"
                spellCheck={false}
                className="w-full max-w-md rounded-md border border-border/50 bg-term-bg px-3 py-2 font-mono text-sm outline-none focus:border-accent"
                aria-invalid={!!validationError}
                aria-describedby={validationError ? "byok-cli-error" : undefined}
              />
              {validationError ? (
                <p id="byok-cli-error" className="mt-1.5 text-[11px] text-destructive">
                  {validationError}
                </p>
              ) : (
                <p className="mt-1.5 text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  {inputProvider === "openai"
                    ? "OpenAI keys start with sk-"
                    : inputProvider === "anthropic"
                      ? "Anthropic keys start with sk-ant-"
                      : "OpenRouter keys start with sk-or-"}
                </p>
              )}
            </div>

            {inputProvider === "openrouter" ? (
              <div>
                <label
                  htmlFor="byok-cli-model"
                  className="mb-2 block text-[11px] uppercase tracking-wide"
                  style={{ color: "var(--text-secondary)" }}
                >
                  model
                </label>
                <input
                  id="byok-cli-model"
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
                  className="w-full max-w-md rounded-md border border-border/50 bg-term-bg px-3 py-2 font-mono text-sm outline-none focus:border-accent"
                />
                <p className="mt-1.5 text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  OpenRouter model slug (provider/model), e.g. anthropic/claude-sonnet-4
                </p>
              </div>
            ) : null}

            {testResult !== null ? (
              <p
                className="text-[12px] font-mono"
                style={{
                  // error rides the four-state --down (canon §16) — a livery is
                  // an identity, never a semantic
                  color: testResult.ok ? "var(--accent)" : "var(--down, #e0654b)",
                }}
              >
                {testResult.ok
                  ? `ok — connected${testResult.model ? ` (${testResult.model})` : ""}`
                  : `error: ${testResult.error ?? "unknown"}`}
              </p>
            ) : null}
          </div>
        </TermLine>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-border/40 pt-3">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="font-mono text-xs"
          disabled={testing || !inputKey}
          onClick={() => void handleTest()}
        >
          {testing ? <Loader2 className="mr-1.5 size-3 animate-spin" /> : null}
          test
        </Button>
        <Button
          type="button"
          size="sm"
          className="font-mono text-xs"
          disabled={!inputKey}
          onClick={handleSave}
        >
          save
        </Button>
        {isSet ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="font-mono text-xs text-destructive hover:text-destructive"
            onClick={handleClear}
          >
            remove
          </Button>
        ) : null}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="ml-auto font-mono text-xs text-muted-foreground"
          onClick={onClose}
        >
          close · esc
        </Button>
      </div>
    </div>
  );
}
