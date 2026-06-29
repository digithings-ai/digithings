"use client";

import { useCallback, useEffect, useState } from "react";
import {
  PROVIDER_LABELS,
  PROVIDER_MODELS,
  type ProviderId,
  validateProviderKey,
} from "@/lib/providerSettings";

type TestResult = { ok: boolean; model?: string; error?: string } | null;

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
  const [inputKey, setInputKey] = useState(storedKey);
  const [inputProvider, setInputProvider] = useState<ProviderId>(storedProvider);
  const [inputModel, setInputModel] = useState(storedModel);
  const [showKey, setShowKey] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<TestResult>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setInputKey(storedKey);
    setInputProvider(storedProvider);
    setInputModel(storedModel);
    setValidationError(null);
    setTestResult(null);
    setShowKey(false);
  }, [open, storedKey, storedProvider, storedModel]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const handleProviderChange = useCallback((p: ProviderId) => {
    setInputProvider(p);
    setInputModel(PROVIDER_MODELS[p][0]?.id ?? "");
    setTestResult(null);
    if (inputKey) setValidationError(validateProviderKey(inputKey, p));
    else setValidationError(null);
  }, [inputKey]);

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

  if (!open) return null;

  const providers = Object.keys(PROVIDER_MODELS) as ProviderId[];

  return (
    <div className="dc-settings-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="dc-settings-panel"
        role="dialog"
        aria-labelledby="dc-settings-title"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="dc-settings-head">
          <h2 id="dc-settings-title" className="dc-settings-title">
            Bring your own key
          </h2>
          <button type="button" className="dc-settings-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <p className="dc-settings-note">
          Your key stays in this browser only. It is sent per request to route your chat — never
          stored on our servers.
        </p>

        <div className="dc-settings-field">
          <span className="dc-settings-label">Provider</span>
          <div className="dc-settings-providers">
            {providers.map((p) => (
              <button
                key={p}
                type="button"
                className={`dc-settings-provider${inputProvider === p ? " is-active" : ""}`}
                onClick={() => handleProviderChange(p)}
              >
                {PROVIDER_LABELS[p]}
              </button>
            ))}
          </div>
        </div>

        <div className="dc-settings-field">
          <label className="dc-settings-label" htmlFor="dc-byok-key">
            API key
          </label>
          <div className="dc-settings-keyrow">
            <input
              id="dc-byok-key"
              className="dc-settings-input"
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
              placeholder={
                inputProvider === "openrouter"
                  ? "sk-or-v1-…"
                  : inputProvider === "anthropic"
                    ? "sk-ant-…"
                    : inputProvider === "gemini"
                      ? "AI…"
                      : "sk-…"
              }
              autoComplete="off"
              spellCheck={false}
            />
            <button
              type="button"
              className="dc-settings-ghost"
              onClick={() => setShowKey((v) => !v)}
              aria-label={showKey ? "Hide key" : "Show key"}
            >
              {showKey ? "hide" : "show"}
            </button>
          </div>
          {validationError ? (
            <p className="dc-settings-error" role="alert">
              {validationError}
            </p>
          ) : null}
        </div>

        <div className="dc-settings-field">
          <label className="dc-settings-label" htmlFor="dc-byok-model">
            Model
          </label>
          <select
            id="dc-byok-model"
            className="dc-settings-select"
            value={inputModel}
            onChange={(e) => setInputModel(e.target.value)}
          >
            {PROVIDER_MODELS[inputProvider].map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </div>

        {testResult ? (
          <p
            className={testResult.ok ? "dc-settings-test-ok" : "dc-settings-error"}
            role="status"
          >
            {testResult.ok
              ? `Key verified${testResult.model ? ` · ${testResult.model}` : ""}.`
              : testResult.error}
          </p>
        ) : null}

        <div className="dc-settings-actions">
          <button
            type="button"
            className="dc-settings-ghost"
            onClick={() => void handleTest()}
            disabled={testing || !inputKey.trim()}
          >
            {testing ? "testing…" : "test key"}
          </button>
          <button type="button" className="dc-settings-primary" onClick={handleSave}>
            {isSet ? "update" : "save"}
          </button>
          {isSet ? (
            <button type="button" className="dc-settings-ghost" onClick={handleClear}>
              use free pool
            </button>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
