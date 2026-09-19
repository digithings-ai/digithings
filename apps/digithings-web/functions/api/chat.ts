// Cloudflare Pages Function — POST /api/chat
// Retired: digithings marketing chat uses digichat → digigraph (digillm + digivault hub).
// See infra/digichat-digithings/README.md and docs/architecture/digichat-modular-frontend.md.

export async function onRequest(): Promise<Response> {
  return new Response(
    JSON.stringify({
      error: "chat_migrated",
      message:
        "This Pages Function OpenRouter path is retired. Use digichat /embed with backend.type digigraph.",
    }),
    {
      status: 410,
      headers: {
        "content-type": "application/json",
        "cache-control": "no-store",
      },
    },
  );
}
