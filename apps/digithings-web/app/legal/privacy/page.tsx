import type { Metadata } from "next";
import {
  ContactMailto,
  DocumentFrame,
  GlyphList,
  GlyphRow,
  Mono,
  PageTitle,
  Prose,
  Section,
} from "@digithings/ui";
import { DT_CONTACT_EMAIL } from "@/app/_nav";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";

export const metadata: Metadata = {
  title: "privacy — how digithings.ai handles data",
  description:
    "What digithings.ai stores in your browser, what the optional chat sends to providers, and " +
    "how to ask a privacy question.",
};

const EFFECTIVE_DATE = "August 5, 2026";

// /legal/privacy, rebuilt on the document grammar (D1, #4429): one framed
// column, a hairline between sections, the `[*]` row grammar. Four sections —
// the notice, the optional chat, browser storage, and questions — no card
// grid, no alternating bands.
//
// The facts here are the point of the page, so the copy is the checked copy,
// not marketing: only `digichat:provider` and `digichat:model` are written to
// storage (lib/providerSettings.ts), a provider key lives in memory for the tab
// and is never persisted, a key left by an earlier build is purged from local
// and session storage on load (components/LegacyByokPurge.tsx, #2348), and the
// provider list is the five functions/api/byok/test.ts validates
// (openrouter, openai, anthropic, gemini, xai). EFFECTIVE_DATE is unchanged:
// the data flows did not change, only a description of them.
//
// Two mechanism claims were tightened to match the code as it is now, since the
// old /api/chat Pages Function is retired (a 410 stub): key forwarding is
// attributed to "our backend" rather than that Function, and the chat
// rate-limit counter is the chat backend's in-process window
// (digichat/lib/bff-rate-limit.ts) rather than Cloudflare KV.

export default function PrivacyPage() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <DocumentFrame>
          <div className="px-[var(--page-pad)] py-[var(--page-step)]">
            <PageTitle path="legal/privacy" title="How this website handles data.">
              This notice explains what the digithings.ai website stores in your browser and what
              happens when you use its optional chat. It does not cover copies of the open-source
              software that you or another organization run on separate infrastructure.
            </PageTitle>
          </div>

          <Section
            id="what-the-website-handles"
            title="What the website handles"
            lede="There are no advertising pixels or third-party analytics on this site, and you can read it without an account."
          >
            <Prose>
              <p>
                Like most hosted websites, our hosting provider receives ordinary request data
                needed to deliver and protect the site, such as your IP address, requested URL,
                browser information, and request time.
              </p>
            </Prose>
            <GlyphList className="mt-[1.6rem]">
              <GlyphRow label="Effective">{EFFECTIVE_DATE}</GlyphRow>
              <GlyphRow label="Contact">
                <ContactMailto
                  email={DT_CONTACT_EMAIL}
                  className="text-accent [text-underline-offset:2px] hover:text-ink"
                  subject="digithings%20privacy%20question"
                  showAddress
                >
                  {DT_CONTACT_EMAIL}
                </ContactMailto>
              </GlyphRow>
              <GlyphRow label="Software">
                Self-hosted deployments are controlled by their operators, not by this website.
              </GlyphRow>
            </GlyphList>
          </Section>

          <Section
            id="optional-chat"
            title="Optional chat"
            lede="The chat is optional and runs against the provider you choose."
          >
            <GlyphList>
              <GlyphRow label="Messages">
                When you use digichat, your message and the recent conversation are sent through our
                backend to the selected model provider. The provider processes that content under
                its own terms and privacy policy. Do not submit confidential, personal, or regulated
                information that you do not want processed by that provider.
              </GlyphRow>
              <GlyphRow label="Documentation search">
                Questions about digithings may also be sent to our hosted documentation search so the
                assistant can retrieve relevant public project documentation. Search results are
                then included in the request sent to the model provider.
              </GlyphRow>
              <GlyphRow label="Provider keys">
                If you bring your own key, it stays in memory for the current tab. It is never
                written to local storage or any other browser storage, and it is gone when you close
                or refresh the tab. Each chat or key-test request sends it to our backend, which
                forwards it to OpenRouter, OpenAI, Anthropic, Google, or xAI, according to your
                selection. We do not write the key to an application database.
              </GlyphRow>
              <GlyphRow label="Abuse prevention">
                Chat requests are rate-limited by IP address in one-minute windows, using a
                best-effort counter held in the chat backend&rsquo;s process memory. Cloudflare may
                separately process and retain request data according to its own policies as our
                hosting and security provider.
              </GlyphRow>
            </GlyphList>
          </Section>

          <Section
            id="browser-storage"
            title="Browser storage"
            lede="What stays in your browser, and for how long."
          >
            <Prose>
              <p>
                The site stores a small number of preferences in your browser using local storage:
                your colour theme and, if you choose to configure chat, your selected provider and
                model. Those values remain until you remove them through your browser or clear them
                in chat settings. An older version of this site also stored a provider key; that
                legacy entry is no longer read and is deleted from local and session storage when a
                page loads.
              </p>
              <p>
                Chat messages, and any provider key you entered, remain in the current page&rsquo;s
                memory and disappear when that page is closed or refreshed.
              </p>
              <p>
                When the homepage opens a conversation in the full chat page, it temporarily puts
                that conversation in local storage. The chat page reads and deletes it once. If the
                stored handoff is more than five minutes old when read, it is discarded; if the chat
                page never opens, it remains until you clear the site&rsquo;s local data.
              </p>
            </Prose>
          </Section>

          <Section
            id="questions"
            title="Questions and changes"
            lede="We will update this notice when the website's data flows change and revise the effective date above."
          >
            <Prose>
              <p>
                To ask what data we hold about you, request deletion of data we control, or raise
                another privacy question,{" "}
                <ContactMailto
                  email={DT_CONTACT_EMAIL}
                  subject="digithings%20privacy%20request"
                  showAddress
                  ariaLabel="Email us about privacy"
                >
                  email us
                </ContactMailto>
                . We may need enough information to verify and act on the request.
              </p>
              <p>
                For the software&rsquo;s security model and current limitations, read the{" "}
                <a href="/security">security page</a>.
              </p>
              <p>
                The source for this website is public. The relevant implementation lives in{" "}
                <Mono>apps/digithings-web</Mono> in the digithings repository.
              </p>
            </Prose>
          </Section>
        </DocumentFrame>
      </main>

      <DtFooter />
    </>
  );
}
