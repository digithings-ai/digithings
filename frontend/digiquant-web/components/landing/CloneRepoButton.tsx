"use client";

import { useCallback, useState } from "react";
import { GitHubGlyph } from "@digithings/web";

export const DIGIQUANT_GITHUB_ROOT = "https://github.com/digithings-ai/digithings";
export const DIGIQUANT_REPO_URL = `${DIGIQUANT_GITHUB_ROOT}/tree/develop/digiquant`;
export const DIGIQUANT_CLONE_CMD = `git clone ${DIGIQUANT_GITHUB_ROOT}.git`;

export function CloneRepoButton({ className = "btn btn-ghost" }: { className?: string }) {
  const [copied, setCopied] = useState(false);

  const onCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(DIGIQUANT_CLONE_CMD);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2200);
    } catch {
      /* clipboard blocked — user can open the repo link beside this button */
    }
  }, []);

  return (
    <div className="flex w-full justify-start gap-[0.5rem]">
      <button
        type="button"
        className={`${className} min-w-[6.35rem] justify-center px-[0.85rem] font-mono text-[0.72rem] normal-case tracking-normal`.trim()}
        onClick={onCopy}
        aria-label={
          copied ? "Clone command copied to clipboard" : "Copy git clone command for digiquant"
        }
      >
        <span className="whitespace-nowrap">{copied ? "Copied!" : "git clone"}</span>
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
