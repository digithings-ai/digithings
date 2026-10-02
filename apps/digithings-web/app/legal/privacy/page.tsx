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

const EFFECTIVE_DATE = "October 2, 2026";

// Facts checked against the live chat frame, not the retired Pages Function:
// ungated embed is free_then_byok (no key → digigraph on the operator model;
// x-byok-key forwards a visitor key). Theme is dt-theme in this site's
// localStorage. Provider/model is the digichat cookie digichat_byok_pref
// (one year). The key stays in memory. The embed session
// (digichat_embed_session:) keeps up to 40 messages for 24 hours so fullscreen
// continues the same thread. A one-shot digichat:handoff prompt expires in
// five minutes. Legacy keys are still purged on load.

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
            lede="The chat is optional. Without a key of your own, the thread goes to digigraph on the operator's model."
          >
            <GlyphList>
              <GlyphRow label="Messages">
                Without a key of your own, your message and the recent conversation are sent to
                digigraph and answered on the operator&rsquo;s model. If you supply a key, that
                request is forwarded to OpenRouter, OpenAI, Anthropic, Google, or xAI, according to
                your selection. Do not submit confidential, personal, or regulated information you
                do not want processed that way.
              </GlyphRow>
              <GlyphRow label="Documentation search">
                The assistant can call a documentation search. When it does, the question goes to
                our hosted search and the results are included in the model request. Not every reply
                uses that tool.
              </GlyphRow>
              <GlyphRow label="Provider keys">
                If you bring your own key, it stays in memory for the current tab. It is never
                written to local storage, cookies, or an application database, and it is gone when
                you close or refresh the tab. Each chat or key-test request sends it to our backend,
                which forwards it to the provider you selected.
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
                This site stores your colour theme in local storage (<Mono>dt-theme</Mono>) until
                you clear it. Scroll position for a visit is kept in session storage and disappears
                when the tab closes. An older build stored a provider key; that entry is no longer
                read and is deleted from local and session storage when a page loads.
              </p>
              <p>
                The chat frame, which may be a different origin from this page, stores the current
                conversation in its own local storage (<Mono>digichat_embed_session:</Mono>) for up
                to 24 hours and at most 40 messages, so opening the full chat page continues the
                same session. It also stores a web-search on/off flag and a free-turn counter. Your
                selected provider and model are a cookie on that origin (<Mono>digichat_byok_pref</Mono>),
                kept for one year. The key itself is not in that cookie.
              </p>
              <p>
                A prompt that opens chat from a module card is written once to this site&rsquo;s
                local storage (<Mono>digichat:handoff</Mono>). The chat frame reads it and deletes
                it. If it is more than five minutes old, it is discarded.
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
