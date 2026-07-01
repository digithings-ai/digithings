/**
 * Map `/api/chat` failures to embed-friendly copy (REM-010).
 */
export function formatEmbedChatError(error: Error | undefined): string | null {
  if (!error?.message) return null;
  const raw = error.message.trim();
  let code: string | undefined;
  try {
    const parsed = JSON.parse(raw) as { error?: string; message?: string };
    code = parsed.error;
    if (parsed.message && (code === "embed_disabled" || code === "unauthorized")) {
      return parsed.message;
    }
  } catch {
    // not JSON — fall through
  }
  if (raw.includes("embed_disabled") || code === "embed_disabled") {
    return "Embed chat is not enabled on this host. Set DIGICHAT_EMBED_ENABLED=1 or configure X-Embed-Token.";
  }
  if (raw.includes("unauthorized") || code === "unauthorized") {
    return "Sign in on chat.digithings.ai or add your own API key below.";
  }
  return raw.length > 240 ? `${raw.slice(0, 240)}…` : raw;
}
