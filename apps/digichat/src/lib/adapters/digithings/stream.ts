import {
  convertToModelMessages,
  createUIMessageStream,
  createUIMessageStreamResponse,
  type UIMessage,
} from "ai";
import {
  digigraphChatCompletionsUrl,
  digigraphModelName,
} from "@/lib/digigraph";
import { stripToolDumpFromAnswerDelta } from "@/lib/adapters/digithings/strip-tool-dump";
import { coreMessagesToDigigraphOpenAi } from "@/lib/digigraph-messages";
import { type ActivityDetail } from "@/lib/chat-activity";
import { mapDigigraphTraceToSpans } from "@/lib/adapters/digithings/activity";
import {
  closeOpenReasoning,
  createActivityWriteContext,
  finishStandardActivity,
  uiMessagesForUpstream,
  writeStandardActivity,
} from "@/lib/ui-stream-parts";
import { BYOK_MODEL_REMEDIABLE_CODES } from "@/lib/embed-chat-error";
import { CredentialRedirectError, fetchGuarded } from "@/lib/fetch-guarded";

export type DigigraphTracePayload = {
  v?: number;
  type: string;
  /** Originating vertical or hub: digigraph | digisearch | digiquant */
  service?: string;
  payload?: Record<string, unknown>;
  workflow_id?: string;
  request_id?: string;
  session_id?: string;
};

/** Typed digichat contract from digigraph SSE `delta.digigraph_error`. */
export type DigigraphErrorPayload = {
  code?: string;
  message?: string;
  detail?: string;
};

/** Map digigraph's `{ code, message }` to embed-chat-error's `{ error, message }`. */
export function digigraphErrorToEmbedPayload(err: DigigraphErrorPayload): string {
  const code = typeof err.code === "string" && err.code.length ? err.code : "digigraph_error";
  const payload: { error: string; message?: string; detail?: string } = { error: code };
  // BYOK remediable codes carry trusted copy in embed-chat-error — never relay
  // digigraph's message (it can echo caller headers or other upstream detail).
  if (
    typeof err.message === "string" &&
    err.message.length &&
    !BYOK_MODEL_REMEDIABLE_CODES.has(code)
  ) {
    payload.message = err.message;
  }
  if (
    typeof err.detail === "string" &&
    err.detail.length &&
    !BYOK_MODEL_REMEDIABLE_CODES.has(code)
  ) {
    payload.detail = err.detail;
  }
  return JSON.stringify(payload);
}

/**
 * Machine-readable code relayed on a digigraph 429 (#4777). digigraph
 * rate-limits `/v1/chat/completions` per IP with `Retry-After` +
 * `error.code rate_limit_exceeded` (#4776). The code is accurate for any 429
 * by status alone, so the branch never parses the body — a proxy-generated
 * 429 with an empty body still renders retry copy instead of UNAVAILABLE.
 */
export const RATE_LIMIT_RETRY_CODE = "rate_limit_exceeded";

/**
 * Parse a Retry-After header into display seconds. Unlike parseRetryAfterMs
 * (a sleep duration, clamped to the boot window) this is display-only: the
 * real number is shown, unclamped. Returns null when the header is missing or
 * unusable — the caller falls back to copy without a number.
 */
export function retryAfterSeconds(raw: string | null): number | null {
  if (raw === null) return null;
  const value = raw.trim();
  if (!value.length) return null;
  if (/^\d+$/.test(value)) {
    const seconds = Number.parseInt(value, 10);
    if (!Number.isSafeInteger(seconds) || seconds <= 0) return null;
    return seconds;
  }
  const at = Date.parse(value);
  if (Number.isNaN(at)) return null;
  const seconds = Math.ceil((at - Date.now()) / 1000);
  return seconds > 0 ? seconds : null;
}

/**
 * Build the relayed 429 payload: the rate-limit code plus server-composed
 * copy carrying the Retry-After seconds. Composed here — never relayed from
 * the upstream body — so anonymous embed visitors see no upstream text; only
 * the parsed integer crosses the trust boundary. The client renders
 * `message` verbatim (formatEmbedChatError) and the code keeps the
 * rate-limit BYOK policy (shouldSuggestByokOnEmbedError).
 */
export function rateLimitRetryPayload(retryAfter: string | null): string {
  const seconds = retryAfterSeconds(retryAfter);
  const message =
    seconds === null
      ? "Rate limit reached, please try again shortly."
      : `Rate limit reached, retry in ${seconds} second${seconds === 1 ? "" : "s"}.`;
  return digigraphErrorToEmbedPayload({ code: RATE_LIMIT_RETRY_CODE, message });
}

/**
 * The one upstream-body field an embed visitor is allowed to see: a refusal code
 * the frontend already knows how to act on.
 *
 * Everything else about a digigraph error body stays server-side (see the
 * `!res.ok` branch below). These codes are the exception because
 * `BYOK_MODEL_REMEDIABLE_CODES` — the same set, imported rather than copied, so
 * the two cannot drift — is what `embed-chat-error` uses to open the BYOK
 * sequence and to pick the copy. A code with no frontend copy would render as
 * raw JSON, which is worse than the generic message.
 *
 * The code is relayed; the message never is. digigraph's message for
 * `byok_default_model_provider_mismatch` reflects the caller's own
 * `X-BYOK-Provider` header, and a 500 body can carry stack traces and prompt
 * echoes.
 */
function relayableUpstreamCode(body: string): string | null {
  if (!body.length) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null) return null;
  // digibase's json_error_response nests: {"error": {"code": ..., "message": ...}}.
  // Flat {"code": ...} is accepted too, for handlers that answer without it.
  const outer = parsed as { error?: unknown; code?: unknown };
  const inner =
    typeof outer.error === "object" && outer.error !== null
      ? (outer.error as { code?: unknown })
      : undefined;
  const code = typeof inner?.code === "string" ? inner.code : outer.code;
  if (typeof code !== "string" || !BYOK_MODEL_REMEDIABLE_CODES.has(code)) return null;
  return code;
}

/**
 * User-facing copy for a digigraph failure the visitor can only retry: a
 * non-OK status with no actionable code, an empty body, or a refused
 * credential redirect.
 *
 * Delivered as a stream `error` part (never an assistant `text-delta`) so the
 * runtime marks the assistant message as errored and the error UI + retry
 * shows, instead of a success-looking bubble (#3910).
 */
export const DIGIGRAPH_UNAVAILABLE_MESSAGE =
  "The assistant is unavailable right now. Please try again shortly.";

class DigigraphStreamContractError extends Error {
  constructor(payload: string) {
    super(payload);
    this.name = "DigigraphStreamContractError";
  }
}

const UPSTREAM_MAX_ATTEMPTS = 4;
// Cold starts: the stack worker answers 503 (`stack container not ready`)
// while the container boots; retry until the instance is up.
const UPSTREAM_RETRY_DELAYS_MS = [2000, 5000, 8000];

function retryDelayMs(attempt: number): number {
  const index = Math.min(attempt - 1, UPSTREAM_RETRY_DELAYS_MS.length - 1);
  return UPSTREAM_RETRY_DELAYS_MS[index] ?? 0;
}

/**
 * Machine-readable boot code the stack worker puts on container-not-ready
 * 503s (#4753). ONLY a 503 carrying this code gets the extended boot budget
 * below — every other 503 (real outage, digigraph overload, old plain-text
 * worker body) keeps the ~15s budget above.
 */
export const UPSTREAM_BOOT_RETRY_CODE = "container_booting";

/**
 * Extended retry budget for a booting upstream (#4753). The stack allows
 * portReady 180s + instanceGet 60s, so the budget covers the full ~240s boot
 * window plus margin. Bounded two ways: total elapsed time AND attempt count
 * (Retry-After: 5 polls ~50 times over the window; the attempt cap is the
 * backstop for clock weirdness).
 */
export const UPSTREAM_BOOT_MAX_ELAPSED_MS = 250_000;
export const UPSTREAM_BOOT_MAX_ATTEMPTS = 64;

/** Server-sent Retry-After is honored inside this window (flood/hang guard). */
const BOOT_RETRY_AFTER_MIN_MS = 1_000;
const BOOT_RETRY_AFTER_MAX_MS = 30_000;

/** Fallback boot backoff when the 503 carries no usable Retry-After. */
const BOOT_RETRY_BASE_DELAY_MS = 2_000;

/** True when the 503 body carries the boot code (flat or nested envelope). */
export function isUpstreamBootRetry(bodyText: string): boolean {
  if (!bodyText.length) return false;
  let parsed: unknown;
  try {
    parsed = JSON.parse(bodyText);
  } catch {
    return false;
  }
  if (typeof parsed !== "object" || parsed === null) return false;
  const outer = parsed as { error?: unknown; code?: unknown };
  const code =
    typeof outer.error === "string"
      ? outer.error
      : typeof outer.error === "object" && outer.error !== null
        ? (outer.error as { code?: unknown }).code
        : outer.code;
  return code === UPSTREAM_BOOT_RETRY_CODE;
}

/**
 * Parse a Retry-After header (delta-seconds or HTTP-date) into a clamped
 * delay. Returns null when the header is missing or unusable — the caller
 * falls back to exponential backoff. The server hint is honored exactly
 * (clamped): no jitter, so a booting container is re-polled on its schedule.
 */
export function parseRetryAfterMs(raw: string | null): number | null {
  if (raw === null) return null;
  const value = raw.trim();
  if (!value.length) return null;
  if (/^\d+$/.test(value)) {
    const seconds = Number.parseInt(value, 10);
    if (!Number.isSafeInteger(seconds)) return null;
    return Math.min(Math.max(seconds * 1000, BOOT_RETRY_AFTER_MIN_MS), BOOT_RETRY_AFTER_MAX_MS);
  }
  const at = Date.parse(value);
  if (Number.isNaN(at)) return null;
  const delta = at - Date.now();
  if (delta <= 0) return BOOT_RETRY_AFTER_MIN_MS;
  return Math.min(delta, BOOT_RETRY_AFTER_MAX_MS);
}

/** Exponential fallback with jitter for a boot 503 without Retry-After. */
function bootRetryFallbackDelayMs(bootAttempt: number): number {
  const backoff = Math.min(
    BOOT_RETRY_BASE_DELAY_MS * 2 ** Math.max(bootAttempt - 1, 0),
    BOOT_RETRY_AFTER_MAX_MS,
  );
  return backoff * (0.8 + Math.random() * 0.4);
}

/** Abort-aware sleep so Stop stays responsive between cold-start retries. */
function abortableSleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal?.aborted) {
      resolve();
      return;
    }
    const onAbort = () => {
      clearTimeout(timer);
      resolve();
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

async function* iterateOpenAiSse(
  body: ReadableStream<Uint8Array>,
  onUsage?: (usage: Record<string, unknown>) => void
): AsyncGenerator<Record<string, unknown>> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      for (const line of block.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") continue;
        try {
          const json = JSON.parse(raw) as {
            choices?: Array<{ delta?: Record<string, unknown> }>;
            usage?: Record<string, unknown>;
          };
          if (json.usage && typeof json.usage === "object") {
            onUsage?.(json.usage);
          }
          const delta = json.choices?.[0]?.delta;
          if (delta && Object.keys(delta).length) yield delta;
        } catch {
          /* skip malformed chunk */
        }
      }
    }
  }
}

export async function createDigigraphTraceStreamResponse(opts: {
  messages: UIMessage[];
  digigraphBaseUrl: string;
  /** Includes the upstream `Authorization`; route.ts always builds it. */
  upstreamHeaders: Record<string, string>;
  responseHeaders: Record<string, string>;
  activityDetail: ActivityDetail;
  /** AbortSignal from the inbound request — Stop must cancel the digigraph fetch (#3475). */
  signal?: AbortSignal;
}) {
  const stripped = uiMessagesForUpstream(opts.messages).map((m) => {
    const { id: _omit, ...rest } = m;
    void _omit;
    return rest;
  }) as Omit<UIMessage, "id">[];
  const coreMessages = await convertToModelMessages(stripped, {
    ignoreIncompleteToolCalls: true,
  });
  const url = digigraphChatCompletionsUrl(opts.digigraphBaseUrl);
  const model = digigraphModelName();

  const stream = createUIMessageStream({
    onError: (error) => (error instanceof Error ? error.message : "digigraph stream error"),
    execute: async ({ writer }) => {
      let textSeq = 0;
      let textId = "assistant-main";
      let textOpen = false;
      /** Any answer text was written — the normal success signal. */
      let textEmitted = false;
      const activityCtx = createActivityWriteContext();
      const openText = () => {
        if (textOpen) return;
        closeOpenReasoning(writer, activityCtx);
        textId = textSeq === 0 ? "assistant-main" : `assistant-main-${textSeq}`;
        writer.write({ type: "text-start", id: textId });
        textOpen = true;
      };
      const closeText = () => {
        if (!textOpen) return;
        writer.write({ type: "text-end", id: textId });
        textOpen = false;
        textSeq += 1;
      };
      writer.write({
        type: "data-connection",
        id: "digigraph-connection",
        data: { state: "connecting" },
      });

      // Settle on EVERY exit (error, abort, contract failure), not just the
      // success tail: a part left streaming keeps the thinking animation
      // parked above the final state (foundry wraps the same way).
      try {
      const bodyPayload: Record<string, unknown> = {
        model,
        messages: coreMessagesToDigigraphOpenAi(coreMessages),
        stream: true,
      };
      // #2572: never follow cross-origin redirects while carrying BYOK /
      // LiteLLM / digikey credentials (Node forwards X-* across origins).
      let res: Response;
      // Normal-path attempts (fetch errors + non-boot 503s) keep the ~15s
      // budget (UPSTREAM_MAX_ATTEMPTS + UPSTREAM_RETRY_DELAYS_MS). Boot-coded
      // 503s count separately against UPSTREAM_BOOT_MAX_* (#4753).
      let attempt = 0;
      let bootAttempts = 0;
      let warmingReported = false;
      const loopStartedAtMs = Date.now();
      for (;;) {
        if (opts.signal?.aborted) {
          throw new DOMException("The operation was aborted.", "AbortError");
        }
        try {
          res = await fetchGuarded(url, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              // Authorization comes from upstreamHeaders and nowhere else, because
              // route.ts sets it unconditionally (`route.ts:244`, one const literal;
              // later lines only add X-* keys). NOT because the spread would override
              // it — a spread overrides only keys it actually contains, so an
              // `Authorization` set here WOULD survive a caller that omitted one. That
              // is why route.ts's unconditional set is pinned by a test rather than
              // left to inspection: if it ever becomes conditional, this adapter must
              // regain a fallback or digigraph gets an unauthenticated request (#2537).
              ...opts.upstreamHeaders,
              // After upstreamHeaders so dogfood never inherits Open WebUI format.
              // Belt-and-suspenders: digigraph's Open WebUI chrome is opt-in only
              // (X-Response-Format: openwebui or openwebui_format=true), never implied
              // by model id, but dogfood forces plain explicitly rather than relying
              // on that default.
              "X-Suppress-Tool-Stream": "1",
              "X-Response-Format": "plain",
            },
            body: JSON.stringify(bodyPayload),
            signal: opts.signal,
          });
        } catch (err) {
          if (err instanceof CredentialRedirectError) {
            console.error(`[digigraph] credential redirect refused: ${err.message}`);
            closeText();
            throw new DigigraphStreamContractError(DIGIGRAPH_UNAVAILABLE_MESSAGE);
          }
          attempt += 1;
          if (attempt >= UPSTREAM_MAX_ATTEMPTS || opts.signal?.aborted) {
            throw err;
          }
          await abortableSleep(retryDelayMs(attempt), opts.signal);
          continue;
        }
        if (res.status === 503) {
          // Read (don't just cancel) the body: the boot code lives in it, and
          // a consumed body is equivalent to a cancelled one for the error
          // path below (`res.text()` on it resolves "" via the catch).
          const bodyText = (await res.text().catch(() => "")).slice(0, 4000);
          if (isUpstreamBootRetry(bodyText) && !opts.signal?.aborted) {
            bootAttempts += 1;
            const remainingMs = UPSTREAM_BOOT_MAX_ELAPSED_MS - (Date.now() - loopStartedAtMs);
            if (bootAttempts < UPSTREAM_BOOT_MAX_ATTEMPTS && remainingMs > 0) {
              if (!warmingReported) {
                warmingReported = true;
                // One line per turn (not per retry): a full boot polls ~50
                // times, and the warming_up stream part is the client signal.
                console.error(
                  `[digigraph] upstream booting (${UPSTREAM_BOOT_RETRY_CODE}); ` +
                    `extended retry budget ${UPSTREAM_BOOT_MAX_ELAPSED_MS}ms`,
                );
                writer.write({
                  type: "data-connection",
                  id: "digigraph-connection",
                  data: { state: "warming_up" },
                });
              }
              const serverDelayMs = parseRetryAfterMs(res.headers.get("retry-after"));
              const delayMs = Math.min(
                serverDelayMs ?? bootRetryFallbackDelayMs(bootAttempts),
                remainingMs,
              );
              await abortableSleep(delayMs, opts.signal);
              continue;
            }
            break;
          }
          attempt += 1;
          if (attempt >= UPSTREAM_MAX_ATTEMPTS) {
            break;
          }
          await abortableSleep(retryDelayMs(attempt), opts.signal);
          continue;
        }
        break;
      }
      if (!res.ok) {
        // Log the upstream detail server-side; never stream it. A 500 body can
        // carry stack traces, internal hostnames, and prompt echoes, and this
        // response goes to anonymous embed visitors.
        const detail = (await res.text().catch(() => "")).trim();
        console.error(
          `[digigraph] upstream ${res.status} ${res.statusText}`,
          detail.length > 1500 ? `${detail.slice(0, 1500)}…` : detail
        );
        if (res.status === 429) {
          // #4777: rate-limited, not down — say when to retry instead of the
          // generic unavailable-message. Status-gated (never body-parsed):
          // digigraph sends Retry-After + error.code rate_limit_exceeded
          // (#4776), but a bare proxy 429 takes the same path. Ahead of the
          // relayable check so the Retry-After seconds survive — that path
          // relays the code alone and would drop the number.
          closeText();
          throw new DigigraphStreamContractError(
            rateLimitRetryPayload(res.headers.get("retry-after")),
          );
        }
        const relayable = relayableUpstreamCode(detail);
        if (relayable) {
          // Actionable refusal: hand the code (never the body) to the client so
          // it can say what to do instead of a dead end. Same mechanism as the
          // `digigraph_error` SSE branch below; both now drop upstream `message`
          // for BYOK remediable codes (embed-chat-error owns that copy).
          closeText();
          throw new DigigraphStreamContractError(
            digigraphErrorToEmbedPayload({ code: relayable })
          );
        }
        // #3910: no actionable code — fail the turn with a real error part so
        // the runtime renders the error UI and a retry, not a fake reply.
        closeText();
        throw new DigigraphStreamContractError(DIGIGRAPH_UNAVAILABLE_MESSAGE);
      }
      writer.write({
        type: "data-connection",
        id: "digigraph-connection",
        data: { state: "connected" },
      });
      if (!res.body) {
        console.error(
          `[digigraph] upstream ${res.status} returned an empty body (reason=empty_body)`
        );
        closeText();
        throw new DigigraphStreamContractError(DIGIGRAPH_UNAVAILABLE_MESSAGE);
      }
      let usageMetadata:
        | { inputTokens: number; outputTokens: number; totalTokens: number }
        | undefined;
      for await (const delta of iterateOpenAiSse(res.body, (usage) => {
        const inputTokens = usage.prompt_tokens;
        const outputTokens = usage.completion_tokens;
        const totalTokens = usage.total_tokens;
        if (
          typeof inputTokens === "number" &&
          Number.isFinite(inputTokens) &&
          typeof outputTokens === "number" &&
          Number.isFinite(outputTokens)
        ) {
          usageMetadata = {
            inputTokens,
            outputTokens,
            totalTokens:
              typeof totalTokens === "number" && Number.isFinite(totalTokens)
                ? totalTokens
                : inputTokens + outputTokens,
          };
        }
      })) {
        const dgErr = delta.digigraph_error;
        if (dgErr && typeof dgErr === "object") {
          closeText();
          throw new DigigraphStreamContractError(
            digigraphErrorToEmbedPayload(dgErr as DigigraphErrorPayload),
          );
        }
        const reasoning =
          (typeof delta.reasoning_content === "string" && delta.reasoning_content) ||
          (typeof (delta as { reasoning?: unknown }).reasoning === "string"
            ? (delta as { reasoning: string }).reasoning
            : "");
        if (reasoning) {
          closeText();
          writeStandardActivity(
            writer,
            {
              operation: "chat",
              status: "started",
              label: "Thinking",
              reasoningDelta: reasoning,
            },
            activityCtx,
          );
        }
        const c = delta.content;
        if (typeof c === "string" && c.length) {
          const cleaned = stripToolDumpFromAnswerDelta(c);
          if (cleaned.length) {
            openText();
            writer.write({ type: "text-delta", id: textId, delta: cleaned });
            textEmitted = true;
          }
        }
        const tr = delta.digigraph_trace;
        if (tr && typeof tr === "object") {
          const payload = tr as DigigraphTracePayload;

          // #2306 follow-up: a round_boundary trace marks that the content already
          // streamed for that round (if any — digigraph only fires this when the
          // round narrated something) was NOT the final answer, e.g. "I will load
          // the full notes now." written alongside that round's tool calls. Without
          // this, that narration and the next round's real answer land in the SAME
          // text part with nothing between them — confirmed in production, where
          // they read as one continuous, self-contradicting block ("...I cannot
          // fully answer... [answers fully anyway]"). Closing the current text part
          // and opening a fresh one puts them in separate message parts instead.
          // This is NOT an activity span — it renders no visible chip; it only
          // resets which text part subsequent "content" deltas land in.
          if (payload.type === "round_boundary") {
            closeText();
            continue;
          }

          const spans = mapDigigraphTraceToSpans(payload, opts.activityDetail);
          if (spans.some((s) => s.operation === "execute_tool" || s.operation === "retrieve")) {
            closeText();
          }
          for (const span of spans) {
            writeStandardActivity(writer, span, activityCtx);
          }
        }
      }
      if (usageMetadata) {
        // Real provider-reported token usage: digigraph appends a final SSE
        // chunk carrying top-level `usage` whose prompt/completion tokens came
        // from the LiteLLM stream. Surface it as message metadata so the client
        // folds it into `metadata.custom.usage` (never fabricate zeros).
        writer.write({
          type: "message-metadata",
          messageMetadata: { usage: usageMetadata },
        });
      }
      // #3910: a real 200 always has a non-null body even when the upstream
      // sends no bytes, so `!res.body` only catches 204/205/HEAD. Without this,
      // an SSE stream that ends with zero events completes silently — no
      // assistant text, no activity, no error, no Retry. Treat a stream that
      // produced neither answer text nor any activity/tool part as an upstream
      // failure. `activityCtx.seq` counts every non-text part written (reasoning,
      // tool, source, data-status), so a tool-only or reasoning-only reply is
      // not misclassified as empty.
      if (!textEmitted && activityCtx.seq === 0) {
        console.error(
          `[digigraph] upstream ${res.status} streamed no text or activity (content-type=${res.headers.get("content-type") ?? "none"}; reason=empty_stream)`
        );
        closeText();
        throw new DigigraphStreamContractError(DIGIGRAPH_UNAVAILABLE_MESSAGE);
      }
      } finally {
        // Idempotent when the turn already settled on the success path.
        finishStandardActivity(writer, activityCtx);
        closeText();
      }
    },
  });

  return createUIMessageStreamResponse({ stream, headers: opts.responseHeaders });
}
