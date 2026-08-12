"use client";

import { useCallback, useState } from "react";
import { GitHubGlyph } from "@digithings/web";

export const DIGIQUANT_GITHUB_ROOT = "https://github.com/digithings-ai/digithings";
export const DIGIQUANT_REPO_URL = `${DIGIQUANT_GITHUB_ROOT}/tree/develop/digiquant`;
export const DIGIQUANT_CLONE_CMD = `git clone ${DIGIQUANT_GITHUB_ROOT}.git`;

type CopyStatus = "idle" | "copied" | "failed";

export function CloneRepoButton({ className = "btn btn-ghost" }: { className?: string }) {
  const [status, setStatus] = useState<CopyStatus>("idle");

  const onCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(DIGIQUANT_CLONE_CMD);
      setStatus("copied");
      window.setTimeout(() => setStatus("idle"), 2200);
    } catch {
      // Clipboard blocked (permission denied, insecure context, unsupported
      // browser) -- surface it instead of failing silently (full-UI-suite
      // critique, digiquant-web target, P3); the adjacent GitHub link is
      // the fallback the button now points to.
      setStatus("failed");
      window.setTimeout(() => setStatus("idle"), 3200);
    }
  }, []);

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
