import type { Metadata } from "next";
import Link from "next/link";
import { DtFooter } from "@/components/DtFooter";
import { ContactMailto, Mono, PageHead, RuledList, RuledRow } from "@digithings/ui";
import { DT_CONTACT_EMAIL } from "@/app/_nav";
import { DtNav } from "@/components/DtNav";

export const metadata: Metadata = {
  title: "privacy — how digithings.ai handles data",
  description:
    "What digithings.ai stores in your browser, what the optional chat sends to providers, and " +
    "how to ask a privacy question.",
};

const EFFECTIVE_DATE = "August 5, 2026";

export default function PrivacyPage() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <PageHead kicker={"// privacy"} title="How this website handles data.">
          This notice explains what the digithings.ai website stores in your browser and what
          happens when you use its optional chat. It does not cover a copy of the open-source
          software that you or another organization operate on separate infrastructure.
        </PageHead>

        <section className="section">
          <div className="wrap">
            <span className="kicker">{"// what the website handles"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.75] text-ink-soft">
              We do not use advertising pixels or third-party analytics on this website. You can
              read the site without creating an account. Like most hosted websites, our hosting
              provider receives ordinary request data needed to deliver and protect the site, such
              as your IP address, requested URL, browser information, and request time.
            </p>
            <p className="mt-[1rem] max-w-[64ch] text-[1rem] leading-[1.75] text-ink-soft">
              The site stores a small number of preferences in your browser using local storage:
              your colour theme and, if you choose to configure chat, your selected provider, model,
              and API key. Those values remain in your browser until you clear them. The provider key
              is sent to our Cloudflare Function only when you test it or send a chat request; the
              function forwards it to the provider you selected and does not persist it in an
              application database.
            </p>
            <RuledList>
              <RuledRow term="Effective">{EFFECTIVE_DATE}</RuledRow>
              <RuledRow term="Contact">
                <ContactMailto email={DT_CONTACT_EMAIL}
                  className="text-accent [text-underline-offset:2px] hover:text-ink"
                  subject="digithings%20privacy%20question"
                  showAddress
                >
                  {DT_CONTACT_EMAIL}
                </ContactMailto>
              </RuledRow>
              <RuledRow term="Software">
                Self-hosted deployments are controlled by their operators, not by this website.
              </RuledRow>
            </RuledList>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <span className="kicker">{"// optional chat"}</span>
            <RuledList className="mt-[1.2rem]">
                <RuledRow term="Messages">
                  <p>
                    When you use digichat, your message and the recent conversation are sent through
                    our Cloudflare Function to the selected model provider. The provider processes
                    that content under its own terms and privacy policy. Do not submit confidential,
                    personal, or regulated information that you do not want processed by that
                    provider.
                  </p>
                </RuledRow>
                <RuledRow term="Documentation search">
                  <p>
                    Questions about digithings may also be sent to our hosted documentation search
                    so the assistant can retrieve relevant public project documentation. Search
                    results are then included in the request sent to the model provider.
                  </p>
                </RuledRow>
                <RuledRow term="Provider keys">
                  <p>
                    If you bring your own key, it is stored in local storage in your browser. Each
                    chat or key-test request sends it through our Function to OpenRouter, OpenAI,
                    Anthropic, or Google, according to your selection. We do not write the key to an
                    application database.
                  </p>
                </RuledRow>
                <RuledRow term="Abuse prevention">
                  <p>
                    Chat requests are rate-limited by IP address in one-minute windows. The counter
                    uses either Cloudflare KV with a two-minute expiry or a best-effort in-memory
                    fallback. Cloudflare may separately process and retain request data according to
                    its own policies as our hosting and security provider.
                  </p>
                </RuledRow>
            </RuledList>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <span className="kicker">{"// browser storage"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.75] text-ink-soft">
              Theme and chat-provider settings remain until you remove them through your browser or
              clear the saved key in chat settings. Chat messages normally remain in the current
              page&rsquo;s memory and disappear when that page is closed or refreshed.
            </p>
            <p className="mt-[1rem] max-w-[64ch] text-[1rem] leading-[1.75] text-ink-soft">
              When the homepage opens a conversation in the full chat page, it temporarily puts that
              conversation in local storage. The chat page reads and deletes it once. If the stored
              handoff is more than five minutes old when read, it is discarded; if the chat page never
              opens, it remains until you clear the site&rsquo;s local data.
            </p>
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <span className="kicker">{"// questions and changes"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.75] text-ink-soft">
              To ask what data we hold about you, request deletion of data we control, or raise
              another privacy question,{" "}
              <ContactMailto email={DT_CONTACT_EMAIL}
                className="text-accent [text-underline-offset:2px] hover:text-ink"
                subject="digithings%20privacy%20request"
                showAddress
                ariaLabel="Email us about privacy"
              >
                email us
              </ContactMailto>
              . We may need enough information to verify and act on the request.
            </p>
            <p className="mt-[1rem] max-w-[64ch] text-[1rem] leading-[1.75] text-ink-soft">
              We will update this notice when the website&rsquo;s data flows change and revise the
              effective date above. For the software&rsquo;s security model and current limitations,
              read the{" "}
              <Link className="text-accent [text-underline-offset:2px] hover:text-ink" href="/security">
                security page
              </Link>
              .
            </p>
            <p className="mt-[1rem] max-w-[64ch] text-[1rem] leading-[1.75] text-ink-soft">
              The source for this website is public. The relevant implementation lives in{" "}
              <Mono>apps/digithings-web</Mono> in the digithings repository.
            </p>
          </div>
        </section>
      </main>

      <DtFooter />
    </>
  );
}
