"use client";

import { useCallback, useState } from "react";

export const DIGIQUANT_GITHUB_ROOT = "https://github.com/digithings-ai/digithings";
export const DIGIQUANT_REPO_URL = `${DIGIQUANT_GITHUB_ROOT}/tree/develop/digiquant`;
export const DIGIQUANT_CLONE_CMD = `git clone ${DIGIQUANT_GITHUB_ROOT}.git`;

function GitHubGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
      <path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0C17 4.7 18 5 18 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z" />
    </svg>
  );
}

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
    <div className="clone-repo-actions">
      <button
        type="button"
        className={`${className} btn-clone-cmd`.trim()}
        onClick={onCopy}
        aria-label={
          copied ? "Clone command copied to clipboard" : "Copy git clone command for digiquant"
        }
      >
        <span className="btn-clone-cmd-text">{copied ? "Copied!" : "git clone"}</span>
      </button>
      <a
        className="btn btn-ghost btn-icon"
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
