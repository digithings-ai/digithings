"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { GitHubGlyph } from "@digithings/web";

export const DIGIQUANT_GITHUB_ROOT = "https://github.com/digithings-ai/digithings";
export const DIGIQUANT_REPO_URL = `${DIGIQUANT_GITHUB_ROOT}/tree/develop/digiquant`;
export const DIGIQUANT_CLONE_CMD = `git clone ${DIGIQUANT_GITHUB_ROOT}.git`;

type CopyStatus = "idle" | "copied" | "failed";

export function CloneRepoButton({ className = "btn btn-ghost" }: { className?: string }) {
  const [status, setStatus] = useState<CopyStatus>("idle");
  // Tracks the one pending "reset to idle" timer so a second click's status
  // cannot be cut short by the FIRST click's still-scheduled timeout (review
  // finding on PR #2283: two untracked setTimeout calls raced, letting an
  // earlier click force status back to idle while a later click's message
  // was still supposed to be showing).
  const resetTimer = useRef<number | null>(null);
  // Attempt token (CodeRabbit review, PR #2283): navigator.clipboard.writeText
  // is async, so two rapid clicks fire two promises that are not guaranteed
  // to settle in call order (e.g. one hits a permission prompt). Each attempt
  // captures its own token; a result only applies if it is still the LATEST
  // attempt, so a stale, out-of-order completion cannot overwrite a newer
  // click's status.
  const attemptId = useRef(0);

  useEffect(() => () => {
    if (resetTimer.current != null) window.clearTimeout(resetTimer.current);
  }, []);

  const scheduleReset = useCallback((ms: number) => {
    if (resetTimer.current != null) window.clearTimeout(resetTimer.current);
    resetTimer.current = window.setTimeout(() => setStatus("idle"), ms);
  }, []);

  const onCopy = useCallback(async () => {
    const attempt = ++attemptId.current;
    try {
      await navigator.clipboard.writeText(DIGIQUANT_CLONE_CMD);
      if (attemptId.current !== attempt) return;
      setStatus("copied");
      scheduleReset(2200);
    } catch {
      if (attemptId.current !== attempt) return;
      // Clipboard blocked (permission denied, insecure context, unsupported
      // browser) -- surface it instead of failing silently (full-UI-suite
      // critique, digiquant-web target, P3); the adjacent GitHub link is
      // the fallback the button now points to.
      setStatus("failed");
      scheduleReset(3200);
    }
  }, [scheduleReset]);

  return (
    <div className="flex w-full justify-start gap-[0.5rem]">
      <button
        type="button"
        className={`${className} min-w-[6.35rem] justify-center px-[0.85rem] font-mono text-[0.72rem] normal-case tracking-normal`.trim()}
        onClick={onCopy}
        aria-label={
          status === "copied"
            ? "Clone command copied to clipboard"
            : status === "failed"
              ? "Could not copy the clone command — use the GitHub link instead"
              : "Copy git clone command for digiquant"
        }
      >
        <span className="whitespace-nowrap">
          {status === "copied" ? "Copied!" : status === "failed" ? "Copy failed" : "git clone"}
        </span>
      </button>
      <a
        className="btn btn-ghost btn-icon min-w-[3.125rem] flex-none px-[0.65rem]"
        href={DIGIQUANT_REPO_URL}
        target="_blank"
        rel="noopener noreferrer"
        aria-label="View digiquant repository on GitHub"
      >
        <GitHubGlyph />
      </a>
    </div>
  );
}
