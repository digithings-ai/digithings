// Cloudflare Pages Function — POST /api/contact
//
// The landing page's contact form posts here. The function validates the input,
// records the message in the platform log, and (when the binding is present)
// sends a *notification* email to digithings — it never sends mail *as* the
// visitor and never uses their address as a From. The visitor's own address is
// carried in the body/reply-to of the notification so a reply reaches them;
// that is the whole mechanism.
//
// Owner decision (v13 plan, 2026-09-22): record + Cloudflare notification
// email to contact@digithings.ai, never sending as the visitor.
//
// Delivery, in order:
//   1. Always: `console.log` a one-line JSON record (Cloudflare captures it in
//      Workers Logs) — so a message is never silently lost even with no email
//      binding, which is the state of this project today.
//   2. If `env.CONTACT_EMAIL` is bound (a `send_email` binding of the Cloudflare
//      Email Workers kind), also send the notification. Absent that binding the
//      function still returns 200 — the record is the durable part, the email
//      is the convenience.
//
// No database binding exists on this Pages project and none is introduced here:
// a contact note is not worth a D1 dependency, and the owner asked for exactly
// this much.

interface ContactEnv {
  /** Optional `send_email` binding. `.send({...})` returns a promise. */
  CONTACT_EMAIL?: {
    send(message: {
      to: string;
      from: string;
      subject: string;
      text: string;
      replyTo?: string;
    }): Promise<unknown>;
  };
}

interface EventContext {
  request: Request;
  env: ContactEnv;
}

type ContactResult = { ok: boolean; error?: string };

// Where a notification lands. Kept in one place so the form, the function and
// the page's mailto all agree; the page shows the same address verbatim.
const NOTIFY_TO = "contact@digithings.ai";
// From must be an address on a domain the Email Routing binding is verified
// for. `digithings.ai` is; the notification is from the site, not the visitor.
const NOTIFY_FROM = "site@digithings.ai";

const MAX_EMAIL_LEN = 254;
const MAX_MESSAGE_LEN = 5000;
const MIN_MESSAGE_LEN = 10;
// A body larger than this is rejected before any parse work. 8 KB is far above
// a 5 KB message plus an address and JSON overhead; anything bigger is abuse.
const MAX_BODY_BYTES = 8 * 1024;

// Deliberately permissive: the real check is whether a reply ever arrives, and
// a stricter pattern only rejects legitimate addresses. Requires an `@` with
// something either side and a dot in the domain.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function jsonResponse(body: ContactResult, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "x-content-type-options": "nosniff",
      // A contact reply must never be served from cache.
      "cache-control": "no-store",
    },
  });
}

/**
 * Only same-site submissions are accepted. Same rule as the retired BYOK
 * tester: localhost is allowed for `wrangler pages dev`, everything else must
 * match the host it was served from. A cross-site POST is a stranger's form
 * using our endpoint as an open relay.
 */
function sameSiteOK(request: Request): boolean {
  const reqHost = new URL(request.url).hostname;
  if (reqHost === "localhost" || reqHost === "127.0.0.1") return true;
  const origin = request.headers.get("origin");
  if (!origin) return false;
  try {
    return new URL(origin).hostname === reqHost;
  } catch {
    return false;
  }
}

/** Collapse CR/LF so a submitted value cannot inject extra mail headers. */
function oneLine(value: string): string {
  return value.replace(/[\r\n]+/g, " ").trim();
}

export async function onRequestPost(ctx: EventContext): Promise<Response> {
  if (!sameSiteOK(ctx.request)) {
    return jsonResponse({ ok: false, error: "Cross-site requests are not allowed." }, 403);
  }

  const raw = await ctx.request.text();
  if (raw.length > MAX_BODY_BYTES) {
    return jsonResponse({ ok: false, error: "Message is too long." }, 413);
  }

  let parsed: { email?: unknown; message?: unknown };
  try {
    parsed = JSON.parse(raw) as typeof parsed;
  } catch {
    return jsonResponse({ ok: false, error: "Expected a JSON body." }, 400);
  }

  const email = typeof parsed.email === "string" ? oneLine(parsed.email) : "";
  const message = typeof parsed.message === "string" ? parsed.message.trim() : "";

  if (!email || !EMAIL_RE.test(email) || email.length > MAX_EMAIL_LEN) {
    return jsonResponse({ ok: false, error: "A valid email address is required." }, 400);
  }
  if (message.length < MIN_MESSAGE_LEN) {
    return jsonResponse({ ok: false, error: "Tell us a little more." }, 400);
  }
  if (message.length > MAX_MESSAGE_LEN) {
    return jsonResponse({ ok: false, error: "Message is too long." }, 413);
  }

  // 1. The durable record. One line, greppable in Workers Logs. `email` is
  //    included because a contact note without a reply address is useless; the
  //    message body is included because that is the point of the form.
  console.log(
    JSON.stringify({
      kind: "contact",
      at: new Date().toISOString(),
      email,
      message,
    }),
  );

  // 2. The convenience: a notification email, if the binding exists.
  if (ctx.env.CONTACT_EMAIL) {
    try {
      await ctx.env.CONTACT_EMAIL.send({
        to: NOTIFY_TO,
        from: NOTIFY_FROM,
        replyTo: email,
        subject: `digithings contact — ${email}`,
        text: `From: ${email}\n\n${message}\n`,
      });
    } catch (err) {
      // The record above already succeeded. A failed notification must not turn
      // a delivered message into a client-visible error — log and still 200.
      console.error(
        JSON.stringify({
          kind: "contact-email-error",
          at: new Date().toISOString(),
          error: err instanceof Error ? err.message : String(err),
        }),
      );
    }
  }

  return jsonResponse({ ok: true }, 200);
}
