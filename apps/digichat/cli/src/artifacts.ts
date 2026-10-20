/**
 * Session artifacts for the digichat CLI.
 *
 * Parity target: the web chat's `/artifacts` panel (DIG-2784 / DIG-2882). This module
 * deliberately re-implements nothing the server already owns:
 *
 * - the paths are the ones the web panel builds (pinned by a source-conformance test
 *   against `packages/ui/src/components/chat/stock/artifacts-panel.tsx`);
 * - the command name and hint are the shared slash registry's `artifacts` entry
 *   (pinned against `packages/digichat-ui/src/slash-commands.ts`);
 * - **open vs download is decided by the server's per-row `viewable` flag**, which the
 *   web panel also trusts. There is no media-type list in this file, on purpose.
 *
 * Availability mirrors the web: a client with no authenticated session store does not
 * get the command at all (`embed-client.tsx` sets `hasArtifacts: false`). Only a
 * digichat machine key (`digi_live_…`, `requireDigiChatAuth`) reaches these routes.
 */

import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import type { DigichatCliAuth } from "./chat-request.js";

/** Same id/name/hint as the shared slash registry's `artifacts` entry. */
export const ARTIFACTS_COMMAND_NAME = "/artifacts";
export const ARTIFACTS_COMMAND_HINT = "Files this session produced";

export const ARTIFACTS_DISPATCH_OPENED = "opened" as const;
export const ARTIFACTS_DISPATCH_DOWNLOADED = "downloaded" as const;

export type CliArtifactDispatch =
  | typeof ARTIFACTS_DISPATCH_OPENED
  | typeof ARTIFACTS_DISPATCH_DOWNLOADED;

export type CliArtifactRow = {
  id: string;
  token: string;
  name: string;
  mediaType: string;
  byteSize: number;
  kind: string;
  summary: string | null;
  createdAt: string;
  /** Server-computed by `isViewable`. Never recomputed here. */
  viewable: boolean;
};

export type CliFetch = (url: string, init?: RequestInit) => Promise<Response>;

/** `status` is 0 when no HTTP call was made (local refusal, no machine key). */
export class CliArtifactRequestError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "CliArtifactRequestError";
    this.status = status;
  }
}

export function artifactsAvailable(auth: DigichatCliAuth): boolean {
  return auth.kind === "api_key";
}

export function conversationCreateUrl(baseUrl: string): string {
  return `${origin(baseUrl)}/api/conversations`;
}

export function artifactListUrl(baseUrl: string, conversationId: string): string {
  return `${origin(baseUrl)}/api/conversations/${encodeURIComponent(conversationId)}/artifacts`;
}

export function artifactBlobUrl(
  baseUrl: string,
  conversationId: string,
  token: string,
): string {
  return `${artifactListUrl(baseUrl, conversationId)}/blob?token=${encodeURIComponent(token)}`;
}

function origin(baseUrl: string): string {
  return new URL(baseUrl).origin;
}

function artifactHeaders(auth: DigichatCliAuth, json: boolean): Record<string, string> {
  if (auth.kind !== "api_key") {
    throw new CliArtifactRequestError(
      "The /artifacts command needs a digichat machine key (DIGICHAT_API_KEY=digi_live_...).",
      0,
    );
  }
  return {
    accept: "application/json",
    "x-digi-caller": "digichat-cli",
    authorization: `Bearer ${auth.apiKey}`,
    ...(json ? { "content-type": "application/json" } : {}),
  };
}

/**
 * Create the conversation this session's artifacts hang off. The store mints nothing
 * on our behalf: `createConversation` takes the caller's id, which is what lets the
 * terminal keep one session id across a chat turn and an artifact lookup.
 */
export async function ensureConversation(opts: {
  baseUrl: string;
  auth: DigichatCliAuth;
  conversationId: string;
  title?: string;
  fetchImpl?: CliFetch;
}): Promise<boolean> {
  const fetchImpl = opts.fetchImpl ?? (globalThis.fetch as CliFetch);
  const body: Record<string, string> = { id: opts.conversationId };
  if (opts.title) body.title = opts.title;

  const res = await fetchImpl(conversationCreateUrl(opts.baseUrl), {
    method: "POST",
    headers: artifactHeaders(opts.auth, true),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new CliArtifactRequestError(
      `Could not create the session store (HTTP ${res.status}).`,
      res.status,
    );
  }
  const payload = (await res.json().catch(() => null)) as { id?: string } | null;
  if (payload?.id && payload.id !== opts.conversationId) {
    throw new CliArtifactRequestError(
      `The server stored a different session id (${payload.id}).`,
      res.status,
    );
  }
  return true;
}

/** List the session's artifacts exactly as the web panel lists them. */
export async function listSessionArtifacts(opts: {
  baseUrl: string;
  auth: DigichatCliAuth;
  conversationId: string;
  fetchImpl?: CliFetch;
}): Promise<CliArtifactRow[]> {
  const fetchImpl = opts.fetchImpl ?? (globalThis.fetch as CliFetch);
  const res = await fetchImpl(artifactListUrl(opts.baseUrl, opts.conversationId), {
    method: "GET",
    headers: artifactHeaders(opts.auth, false),
  });
  if (!res.ok) {
    throw new CliArtifactRequestError(
      `Could not load this session's files (HTTP ${res.status}).`,
      res.status,
    );
  }
  const payload = (await res.json().catch(() => null)) as { artifacts?: unknown } | null;
  const artifacts = payload?.artifacts;
  if (!Array.isArray(artifacts)) {
    throw new CliArtifactRequestError("The artifacts response had no file list.", res.status);
  }
  return artifacts as CliArtifactRow[];
}

export type CliArtifactOsDeps = {
  baseUrl: string;
  conversationId: string;
  /**
   * Hand a fetched file to the OS. `target` is the blob URL; the default seam turns it
   * into a local file first (the route needs the machine key) and opens that.
   */
  openInOs: (target: string, name?: string) => void | Promise<void>;
  /** Save a fetched file into the user's download folder. */
  download: (target: string, name?: string) => void | Promise<void>;
};

/**
 * Move the row cursor by `delta`, wrapping at both ends.
 *
 * Pure so the TUI's arrow handling is testable without a TTY, and so the wrap
 * rule lives in exactly one place. `-1` means "nothing selectable" — an empty
 * list, which is what the panel renders as its empty state.
 */
export function nextArtifactIndex(
  current: number,
  delta: number,
  length: number,
): number {
  if (length <= 0) return -1;
  return (((current + delta) % length) + length) % length;
}

/**
 * Open vs download is the server's call. This function is the whole dispatch and it
 * reads exactly one field: `row.viewable`.
 */
export async function openArtifact(
  row: CliArtifactRow,
  deps: CliArtifactOsDeps,
): Promise<CliArtifactDispatch> {
  const url = artifactBlobUrl(deps.baseUrl, deps.conversationId, row.token);
  if (row.viewable) {
    await deps.openInOs(url, row.name);
    return ARTIFACTS_DISPATCH_OPENED;
  }
  await deps.download(url, row.name);
  return ARTIFACTS_DISPATCH_DOWNLOADED;
}

/** What the panel calls when the user moves the cursor and presses enter. */
export function openArtifactAt(
  rows: CliArtifactRow[],
  index: number,
  deps: CliArtifactOsDeps,
): Promise<CliArtifactDispatch> {
  const row = rows[index];
  if (!row) throw new CliArtifactRequestError("No such file in this session.", 0);
  return openArtifact(row, deps);
}

/**
 * Real OS seams. The blob route needs the machine key, so the bytes are fetched here
 * and handed to the OS as a local file; a viewer can never fetch the URL itself.
 */
export function createOsArtifactDeps(opts: {
  baseUrl: string;
  auth: DigichatCliAuth;
  conversationId: string;
  fetchImpl?: CliFetch;
  downloadDir?: string;
  spawnImpl?: typeof spawn;
}): CliArtifactOsDeps {
  const fetchImpl = opts.fetchImpl ?? (globalThis.fetch as CliFetch);
  const spawnImpl = opts.spawnImpl ?? spawn;
  const downloadDir =
    opts.downloadDir ??
    process.env["DIGICHAT_DOWNLOAD_DIR"] ??
    join(homedir(), "Downloads");

  const toFile = async (url: string, dir: string, name: string): Promise<string> => {
    const res = await fetchImpl(url, {
      method: "GET",
      headers: artifactHeaders(opts.auth, false),
    });
    if (!res.ok) {
      throw new CliArtifactRequestError(
        `Could not read the file (HTTP ${res.status}).`,
        res.status,
      );
    }
    const bytes = Buffer.from(await res.arrayBuffer());
    await mkdir(dir, { recursive: true });
    const safe = name.replace(/[^\w.\-]+/g, "_") || "artifact";
    const path = join(dir, safe);
    await writeFile(path, bytes);
    return path;
  };

  return {
    baseUrl: opts.baseUrl,
    conversationId: opts.conversationId,
    // Viewable files open from a staging copy; everything else lands in Downloads.
    openInOs: (url: string, name?: string) =>
      toFile(url, tmpdir(), name ?? "artifact").then((path) => openPath(path, spawnImpl)),
    // The seam reports through its return value, so the written path is not
    // leaked into the panel; the panel names the destination folder itself.
    download: async (url: string, name?: string) => {
      await toFile(url, downloadDir, name ?? "artifact");
    },
  };
}

function openPath(path: string, spawnImpl: typeof spawn): void {
  const cmd =
    process.platform === "darwin" ? "open" : process.platform === "win32" ? "start" : "xdg-open";
  const child = spawnImpl(cmd, [path], { stdio: "ignore", detached: true });
  child.unref();
}
