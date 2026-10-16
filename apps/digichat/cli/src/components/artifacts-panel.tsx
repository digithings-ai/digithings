/**
 * Terminal view of the session's artifacts — the /artifacts command the web
 * chat already has (`packages/digichat-ui/src/slash-commands.ts`, id
 * "artifacts", same `/artifacts` name and hint; pinned by a source-conformance
 * test so this file cannot drift into a TUI-only shape).
 *
 * Parity rules this file keeps, deliberately:
 *  - it reads ONLY the fields the store returns, including the server-computed
 *    `viewable` flag. There is no media-type list here, so the row decides
 *    open-vs-download exactly as `artifacts-panel.tsx` does in the web leaf;
 *  - its wording for "cannot load" / "nothing yet" is the web panel's wording;
 *  - it is a view over `GET /api/conversations/{id}/artifacts`, the same route,
 *    the same machine key, the same ownership check. No store change was needed
 *    for the terminal.
 *
 * Enter on a row calls `openArtifactAt`, which is the tested dispatch; the OS
 * seams come from `createOsArtifactDeps` so this component never opens a socket
 * itself in tests.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Box, Text, useInput } from "ink";
import {
  ARTIFACTS_COMMAND_HINT,
  ARTIFACTS_DISPATCH_OPENED,
  artifactsAvailable,
  createOsArtifactDeps,
  ensureConversation,
  listSessionArtifacts,
  nextArtifactIndex,
  openArtifactAt,
  type CliArtifactRow,
} from "../artifacts.js";
import type { DigichatCliRequestOptions } from "../chat-request.js";

const ARTIFACT_TITLE = `${ARTIFACTS_COMMAND_HINT}`;
const UNAVAILABLE =
  `This CLI has no session-store credential, so ${"/artifacts"} is not available here.`;
const LOADING = "Loading this session's files…";
const LOAD_FAILED = "Could not load this session's files.";
const EMPTY = "No files in this session yet.";

export function ArtifactsPanel({
  request,
  onClose,
}: {
  request: DigichatCliRequestOptions;
  onClose: () => void;
}) {
  const available = artifactsAvailable(request.auth);
  const conversationId = request.conversationId ?? "";
  const [rows, setRows] = useState<CliArtifactRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cursor, setCursor] = useState(0);
  const [status, setStatus] = useState<string | null>(null);

  const deps = useMemo(
    () =>
      available && conversationId
        ? createOsArtifactDeps({
            baseUrl: request.baseUrl,
            auth: request.auth,
            conversationId,
          })
        : null,
    [available, conversationId, request.baseUrl, request.auth],
  );

  const load = useCallback(async () => {
    if (!deps) return;
    setRows(null);
    setError(null);
    try {
      // The artifacts table has a foreign key onto conversations, so the
      // session's conversation must exist before anything can hang off it.
      // The web client does the same POST before its first artifact; re-posting
      // an existing id would be a duplicate-key insert, so it runs once per
      // session id only.
      await ensureConversation({
        baseUrl: request.baseUrl,
        auth: request.auth,
        conversationId,
        title: "digichat cli",
      });
      setRows(
        await listSessionArtifacts({
          baseUrl: request.baseUrl,
          auth: request.auth,
          conversationId,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRows([]);
    }
  }, [deps, request.baseUrl, request.auth, conversationId]);

  useEffect(() => {
    void load();
  }, [load]);

  useInput((input, key) => {
    if (key.escape || input === "q") {
      onClose();
      return;
    }
    if (input === "r") {
      void load();
      return;
    }
    const count = rows?.length ?? 0;
    if (key.upArrow) {
      setCursor((c) => nextArtifactIndex(c, -1, count));
      return;
    }
    if (key.downArrow) {
      setCursor((c) => nextArtifactIndex(c, 1, count));
      return;
    }
    if (key.return) {
      if (!rows || !deps) return;
      const row = rows[cursor];
      if (!row) return;
      setStatus(null);
      void Promise.resolve(openArtifactAt(rows, cursor, deps))
        .then((dispatch) =>
          setStatus(
            dispatch === ARTIFACTS_DISPATCH_OPENED
              ? `Opened ${row.name} in your default app.`
              : `Saved ${row.name} to your downloads folder.`,
          ),
        )
        .catch((e: unknown) =>
          setError(e instanceof Error ? e.message : String(e)),
        );
    }
  });

  if (!available || !deps) {
    return (
      <Box flexDirection="column" marginTop={1}>
        <Text bold color="cyan">
          {ARTIFACT_TITLE}
        </Text>
        <Text>{UNAVAILABLE}</Text>
        <Text dimColor>
          {"  a digichat machine key (DIGICHAT_API_KEY=digi_live_…) is what the web embed client also lacks"}
        </Text>
        <Text dimColor>{"  q — back to the chat"}</Text>
      </Box>
    );
  }

  if (error) {
    return (
      <Box flexDirection="column" marginTop={1}>
        <Text bold color="cyan">
          {ARTIFACT_TITLE}
        </Text>
        <Text color="red">{LOAD_FAILED}</Text>
        <Text dimColor>{`  ${error}`}</Text>
        <Text dimColor>{"  r — reload · q — back to the chat"}</Text>
      </Box>
    );
  }

  if (rows === null) {
    return (
      <Box flexDirection="column" marginTop={1}>
        <Text bold color="cyan">
          {ARTIFACT_TITLE}
        </Text>
        <Text>{LOADING}</Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" marginTop={1}>
      <Text bold color="cyan">
        {ARTIFACT_TITLE}
      </Text>
      {rows.length === 0 ? (
        <Text>{EMPTY}</Text>
      ) : (
        rows.map((row, i) => (
          <Text key={row.id} color={i === cursor ? "green" : undefined}>
            {i === cursor ? "> " : "  "}
            {row.name}
            <Text dimColor>{`  ${row.kind} · ${row.mediaType} · ${row.byteSize} B`}</Text>
          </Text>
        ))
      )}
      {status ? <Text color="green">{status}</Text> : null}
      <Text dimColor>
        {rows.length > 0
          ? "↑↓ select · Enter opens or saves the file · q — back to the chat"
          : "q — back to the chat"}
      </Text>
    </Box>
  );
}
