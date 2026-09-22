"use client";

import { useState } from "react";
import { Button } from "@digithings/ui/ui";
import { GROUPED_LABEL } from "./label";

/**
 * ContactForm — the landing page's contact box (v13, stage 13, #4429).
 *
 * Owner direction (verbatim intent): "before the contact section… we could have
 * a text box for the message. They put in their email and that should be enough
 * to send out an email directly through the website."
 *
 * It posts to the site's own Pages Function (`functions/api/contact.ts`), which
 * records the note and sends a *notification* to contact@digithings.ai — it does
 * not send mail as the visitor, and no third-party form service is involved.
 * The email field is the visitor's own so a reply reaches them; that is why it
 * is required and shown in the success state.
 *
 * No email address is stored client-side, nothing is prefilled, and the inputs
 * are never persisted — the same posture as the BYOK field elsewhere on the
 * page. The app is a static export, so this is the only island on the page that
 * *needs* to be a client component for a network POST.
 */

type State =
  | { kind: "idle" }
  | { kind: "sending" }
  | { kind: "sent" }
  | { kind: "error"; message: string };

export function ContactForm({ className }: { className?: string }) {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (state.kind === "sending") return;
    setState({ kind: "sending" });
    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, message }),
      });
      const body = (await res.json().catch(() => null)) as
        | { ok?: boolean; error?: string }
        | null;
      if (res.ok && body?.ok) {
        setState({ kind: "sent" });
        setEmail("");
        setMessage("");
        return;
      }
      setState({ kind: "error", message: body?.error ?? "Something went wrong. Email us instead." });
    } catch {
      setState({ kind: "error", message: "Network error. Email us instead." });
    }
  }

  if (state.kind === "sent") {
    return (
      <div className={className}>
        <p className="m-0 font-mono text-[0.85rem] leading-[1.7] text-ink">
          Sent. We will reply to the address you gave.
        </p>
        <p className="mt-[0.6rem] mb-0 font-mono text-[0.75rem] text-ink-mute">
          Nothing else was stored beyond the message itself.
        </p>
      </div>
    );
  }

  return (
    <form className={className} onSubmit={submit}>
      <label className={`block ${GROUPED_LABEL}`} htmlFor="contact-email">
        your email
      </label>
      <input
        id="contact-email"
        name="email"
        type="email"
        required
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@example.com"
        className="mt-[0.4rem] w-full border border-hair bg-surface px-[0.8rem] py-[0.7rem] font-mono text-[0.85rem] text-ink outline-none placeholder:text-ink-mute focus-visible:border-accent"
      />

      <label className={`mt-[1.2rem] block ${GROUPED_LABEL}`} htmlFor="contact-message">
        message
      </label>
      <textarea
        id="contact-message"
        name="message"
        required
        rows={5}
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="What are you running today, and what would you like to build?"
        className="mt-[0.4rem] w-full resize-y border border-hair bg-surface px-[0.8rem] py-[0.7rem] font-mono text-[0.85rem] leading-[1.7] text-ink outline-none placeholder:text-ink-mute focus-visible:border-accent"
      />

      {state.kind === "error" ? (
        <p role="alert" className="mt-[0.8rem] mb-0 font-mono text-[0.78rem] text-warn">
          {state.message}
        </p>
      ) : null}

      <div className="mt-[1rem] flex items-center gap-[0.8rem]">
        <Button type="submit" variant="default" disabled={state.kind === "sending"}>
          {state.kind === "sending" ? "Sending…" : "Send"}
        </Button>
        <span className="font-mono text-[0.72rem] text-ink-mute">
          Goes to contact@digithings.ai — no form service in between.
        </span>
      </div>
    </form>
  );
}
