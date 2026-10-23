"use client";

/**
 * Session artifact surface (DIG-2882, over DIG-2784 / PR #5390).
 *
 * Two client surfaces live here because they answer the same question from
 * opposite ends: `/artifacts` lists what this session produced, and a link the
 * model embedded in a reply opens one of those rows.
 *
 * **Every media-type decision is the server's.** The list route answers with a
 * `viewable` flag it computed from its own inline list; this file never
 * re-derives it, so the browser and the `Content-Disposition` the blob route
 * sends can never disagree about the same row.
 *
 * **Link lifetime is the server's too.** `bindLink` binds a token to a session
 * and the blob route answers `410 session_expired` for a token the session no
 * longer owns. A dead token is therefore a normal outcome here, not an error
 * to dump at the reader - see `ArtifactLink`.
 */

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";
import { p, stripBasePath } from "../../../lib/base-path";
import { StateBlock } from "../../desk/StateBlock";

/** The list route the server already ships (see `.../artifacts/route.ts`). */
export type ArtifactRow = {
  id: string;
  /** The token the store minted. Present on the list row, so no minting here. */
  token: string;
  name: string;
  mediaType: string;
  byteSize: number;
  kind: string;
  summary: string | null;
  createdAt: string | number | Date;
  /** Server-computed. Never recomputed client-side. */
  viewable: boolean;
};

/**
 * `GET /api/conversations/[id]/artifacts` - the panel's only read.
 *
 * The path carries the base path the app is served under (DIG-5121): the app
 * answers under /chat/api/conversations/… and nowhere else, so a
 * root-absolute path would 404 the moment the app moves.
 */
export function artifactListPath(conversationId: string): string {
  return p(`/api/conversations/${encodeURIComponent(conversationId)}/artifacts`);
}

/** The link target, carrying the token the store minted. */
export function artifactBlobPath(conversationId: string, token: string): string {
  return `${artifactListPath(conversationId)}/blob?token=${encodeURIComponent(token)}`;
}

const BLOB_PATH = /^\/api\/conversations\/[^/]+\/artifacts\/blob$/;

/**
 * True when an href is a session artifact link. Pure string work on the path
 * so it runs identically in the browser and in a test - `new URL(href, base)`
 * would make an href without a scheme host-dependent, and a link that is
 * "maybe an artifact" depending on where it was parsed is not a predicate.
 *
 * The base path is stripped first: the app hands out the link already
 * prefixed (/chat/api/conversations/…), and the predicate is about the app's
 * own path, not about where the app happens to be served.
 */
export function isArtifactBlobHref(href: string | undefined | null): boolean {
  if (!href) return false;
  const path = href.split(/[?#]/, 1)[0] ?? "";
  return BLOB_PATH.test(stripBasePath(path));
}

/** Deterministic, locale-free size label. Never used to decide anything. */
export function formatArtifactSize(byteSize: number): string {
  if (!Number.isFinite(byteSize) || byteSize < 0) return "-";
  if (byteSize < 1024) return `${Math.trunc(byteSize)} B`;
  const units = ["KB", "MB", "GB"];
  let value = byteSize / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rounded = Math.round(value * 10) / 10;
  return `${rounded} ${units[unit]}`;
}

/** ISO date if we can get one, else the raw value. Never throws. */
export function formatArtifactDate(createdAt: string | number | Date): string {
  const d = createdAt instanceof Date ? createdAt : new Date(createdAt);
  return Number.isNaN(d.getTime()) ? "-" : d.toISOString().slice(0, 10);
}

/** Injectable seams so tests never need a network or a real `window`. */
export type ArtifactIo = {
  fetchImpl?: typeof fetch;
  /** Opens the blob in a new tab. Return false if the browser refused. */
  openInNewTab?: (url: string) => boolean;
  /** Same-tab fallback when a new tab was refused or is not wanted. */
  navigate?: (url: string) => void;
};

function defaultOpenInNewTab(url: string): boolean {
  const w = window.open(url, "_blank", "noopener,noreferrer");
  return typeof w !== "undefined" && w !== null;
}

function defaultNavigate(url: string): void {
  window.location.assign(url);
}

export function ArtifactsPanel({
  conversationId,
  open,
  onClose,
  fetchImpl,
  openInNewTab = defaultOpenInNewTab,
  navigate = defaultNavigate,
}: ArtifactIo & {
  conversationId: string | null;
  open: boolean;
  onClose: () => void;
}) {
  const [rows, setRows] = useState<ArtifactRow[] | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");

  const load = useCallback(async () => {
    if (!conversationId) {
      setRows([]);
      setState("idle");
      return;
    }
    setState("loading");
    try {
      const doFetch = fetchImpl ?? fetch;
      const res = await doFetch(artifactListPath(conversationId));
      if (!res.ok) {
        setRows(null);
        setState("error");
        return;
      }
      const body = (await res.json()) as { artifacts?: ArtifactRow[] };
      const artifacts = Array.isArray(body.artifacts) ? body.artifacts : [];
      setRows(artifacts);
      setState("idle");
    } catch {
      setRows(null);
      setState("error");
    }
  }, [conversationId, fetchImpl]);

  useEffect(() => {
    if (!open) return;
    void load();
  }, [open, load]);

  if (!open) return null;

  return (
    <div
      className="aui-artifacts-panel border-hair bg-surface-2 fixed inset-y-0 end-0 z-50 flex w-full max-w-sm flex-col border-s"
      data-artifacts-panel=""
      role="dialog"
      aria-label="Session artifacts"
    >
      <header className="border-hair flex items-center justify-between border-b px-4 py-3">
        <h2 className="text-sm font-semibold">Files this session produced</h2>
        <button
          type="button"
          onClick={onClose}
          className="text-ink-mute hover:text-foreground text-sm"
        >
          Close
        </button>
      </header>

      {!conversationId ? (
        <StateBlock
          kind="withheld"
          title="No session store."
          reason="This chat was not opened with a conversation, so it cannot list artifacts."
          className="m-4"
        />
      ) : state === "loading" ? (
        <StateBlock
          kind="loading"
          title="Reading session files."
          className="m-4"
        />
      ) : state === "error" ? (
        <StateBlock
          kind="error"
          title="Could not load this session's files."
          reason="The artifact route did not answer."
          onRetry={() => void load()}
          className="m-4"
        />
      ) : !rows || rows.length === 0 ? (
        <StateBlock
          kind="empty"
          title="No files in this session yet."
          reason="They appear here as the assistant produces them."
          className="m-4"
        />
      ) : (
        <ul className="flex-1 overflow-y-auto">
          {rows.map((row) => (
            <li key={row.id} className="border-hair border-b last:border-b-0">
              <button
                type="button"
                className="flex w-full flex-col gap-1 px-4 py-3 text-start hover:bg-accent/50"
                onClick={() => {
                  const url = artifactBlobPath(conversationId, row.token);
                  // The row decides, via the server's own flag. No media-type
                  // list is duplicated here on purpose.
                  if (row.viewable) {
                    if (!openInNewTab(url)) navigate(url);
                  } else {
                    navigate(url);
                  }
                }}
              >
                <span className="text-sm font-medium">{row.name}</span>
                <span className="text-ink-mute text-xs">
                  {row.mediaType} · {formatArtifactSize(row.byteSize)} ·{" "}
                  {formatArtifactDate(row.createdAt)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * The `a:` override for artifact links in an assistant reply (DoD 3).
 *
 * A session artifact link is clickable and carries the token the store
 * minted. The failure case is the reason this component exists: a dead token
 * answers `410 session_expired`, and following that link normally would show
 * the reader a raw JSON error body. So the click is intercepted, the link is
 * probed, and a dead one becomes a sentence in place instead.
 *
 * Any non-artifact href never reaches here - `markdown-text.tsx` routes on
 * `isArtifactBlobHref` and renders its plain anchor otherwise.
 */
export function ArtifactLink({
  href,
  className,
  children,
  fetchImpl,
  openInNewTab = defaultOpenInNewTab,
  navigate = defaultNavigate,
}: ArtifactIo & {
  href: string;
  className?: string;
  children?: ReactNode;
}) {
  const [expired, setExpired] = useState(false);

  const onClick = useCallback(
    async (event: React.MouseEvent<HTMLAnchorElement>) => {
      event.preventDefault();
      setExpired(false);
      try {
        const doFetch = fetchImpl ?? fetch;
        const res = await doFetch(href, { method: "GET" });
        if (res.status === 410) {
          setExpired(true);
          return;
        }
      } catch {
        // Could not probe: let the browser go to the link rather than guess.
      }
      if (!openInNewTab(href)) navigate(href);
    },
    [href, fetchImpl, openInNewTab, navigate],
  );

  return (
    <>
      <a
        className={cn(
          "aui-md-a text-primary hover:text-primary/80 underline underline-offset-2",
          className,
        )}
        href={href}
        onClick={onClick}
      >
        {children}
      </a>
      {expired ? (
        <span className="aui-artifact-expired text-ink-mute ms-1 text-xs">
          This artifact link belongs to a chat session that has ended. Open
          /artifacts in the current chat to list this session&apos;s files.
        </span>
      ) : null}
    </>
  );
}