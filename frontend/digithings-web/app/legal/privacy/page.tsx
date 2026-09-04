import type { Metadata } from "next";
import Link from "next/link";
import { DtFooter } from "@/components/DtFooter";
import { Mono, PageHead, RuledList, RuledRow } from "../../_company/prose";
import { ContactMailto, Reveal } from "@digithings/web";
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
          <div className="wrap grid gap-[3rem] lg:grid-cols-[minmax(0,1fr)_minmax(17rem,0.42fr)]">
            <div className="max-w-[72ch]">
              <Reveal className="section-head">
                <span className="kicker">{"// what the website handles"}</span>
                <h2>No ad tracking. No account required.</h2>
              </Reveal>
              <p className="mt-[1.1rem] text-[1rem] leading-[1.75] text-ink-soft">
                We do not use advertising pixels or third-party analytics on this website. You can
                read the site without creating an account. Like most hosted websites, our hosting
                provider receives ordinary request data needed to deliver and protect the site,
                such as your IP address, requested URL, browser information, and request time.
              </p>
              <p className="mt-[1rem] text-[1rem] leading-[1.75] text-ink-soft">
                The site stores a small number of preferences in your browser using local storage:
                your colour theme and, if you choose to configure chat, your selected provider,
                model, and API key. Those values remain in your browser until you clear them. The
                provider key is sent to our Cloudflare Function only when you test it or send a chat
                request; the function forwards it to the provider you selected and does not persist
                it in an application database.
              </p>
            </div>

            <aside className="border-t border-hair pt-[1.2rem] lg:border-l lg:border-t-0 lg:pl-[1.6rem] lg:pt-0">
              <span className="block font-mono text-[0.7rem] uppercase tracking-[0.14em] text-ink-mute">
                Notice details
              </span>
              <dl className="mt-[1rem] grid gap-[1rem] text-[0.88rem] leading-[1.6]">
                <div>
                  <dt className="font-mono text-ink-mute">Effective</dt>
                  <dd className="mt-[0.2rem] text-ink">{EFFECTIVE_DATE}</dd>
                </div>
                <div>
                  <dt className="font-mono text-ink-mute">Contact</dt>
                  <dd className="mt-[0.2rem]">
                    <ContactMailto email={DT_CONTACT_EMAIL}
                      className="text-accent [text-underline-offset:2px] hover:text-ink"
                      subject="digithings%20privacy%20question"
                      showAddress
                    >
                      Email us
                    </ContactMailto>
                  </dd>
                </div>
                <div>
                  <dt className="font-mono text-ink-mute">Software</dt>
                  <dd className="mt-[0.2rem] text-ink-soft">
                    Self-hosted deployments are controlled by their operators, not by this website.
                  </dd>
                </div>
              </dl>
            </aside>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// optional chat"}</span>
              <h2>What leaves your browser.</h2>
            </Reveal>
            <div className="mt-[2rem]">
              <RuledList>
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
          </div>
        </section>

        <section className="section">
          <div className="wrap grid gap-[3rem] lg:grid-cols-2">
            <div>
              <Reveal className="section-head">
                <span className="kicker">{"// browser storage"}</span>
                <h2>You control local data.</h2>
              </Reveal>
              <div className="mt-[1.2rem] grid gap-[1rem] text-[1rem] leading-[1.75] text-ink-soft">
                <p>
                  Theme and chat-provider settings remain until you remove them through your browser
                  or clear the saved key in chat settings. Chat messages normally remain in the
                  current page&rsquo;s memory and disappear when that page is closed or refreshed.
                </p>
                <p>
                  When the homepage opens a conversation in the full chat page, it temporarily puts
                  that conversation in local storage. The chat page reads and deletes it once. If
                  the stored handoff is more than five minutes old when read, it is discarded; if
                  the chat page never opens, it remains until you clear the site&rsquo;s local data.
                </p>
              </div>
            </div>

            <div>
              <Reveal className="section-head">
                <span className="kicker">{"// questions and changes"}</span>
                <h2>Ask us directly.</h2>
              </Reveal>
              <div className="mt-[1.2rem] grid gap-[1rem] text-[1rem] leading-[1.75] text-ink-soft">
                <p>
                  To ask what data we hold about you, request deletion of data we control, or raise
                  another privacy question, email{" "}
                  <ContactMailto email={DT_CONTACT_EMAIL}
                    className="text-accent [text-underline-offset:2px] hover:text-ink"
                    subject="digithings%20privacy%20request"
                    showAddress
                  >
                    us
                  </ContactMailto>
                  . We may need enough information to verify and act on the request.
                </p>
                <p>
                  We will update this notice when the website&rsquo;s data flows change and revise
                  the effective date above. For the software&rsquo;s security model and current
                  limitations, read the{" "}
                  <Link
                    className="text-accent [text-underline-offset:2px] hover:text-ink"
                    href="/security"
                  >
                    security page
                  </Link>
                  .
                </p>
                <p>
                  The source for this website is public. The relevant implementation lives in{" "}
                  <Mono>frontend/digithings-web</Mono> in the digithings repository.
                </p>
              </div>
            </div>
          </div>
        </section>
      </main>

      <DtFooter />
    </>
  );
}
