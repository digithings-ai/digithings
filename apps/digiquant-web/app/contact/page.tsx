import type { Metadata } from "next";
import { ContactMailto, DocumentFrame, PageTitle } from "@digithings/ui";
import { CONTACT_MANAGED_FEATURES, CONTACT_SELF_FEATURES, MANAGED_CONTACT_EMAIL, MANAGED_CONTACT_SUBJECT } from "../_contact";

export const metadata: Metadata = {
  title: "Contact — digiquant",
  description:
    "Self-host the full open-core stack for free, or have digiquant managed for you. What's included in each.",
};

const COL =
  "flex min-w-0 flex-col gap-3 border-b border-hair p-[1.3rem] last:border-b-0 lg:border-b-0 lg:border-e lg:last:border-e-0";

export default function ContactPage() {
  return (
    <main id="main" tabIndex={-1}>
      <DocumentFrame>
        <div className="px-[var(--page-pad)] py-[var(--page-step)]">
          <PageTitle title="Contact">
            Self-host the open-core stack, or write about a managed runner. Managed has no price until one is published.
          </PageTitle>
          <div className="mt-8 grid border border-hair lg:grid-cols-2">
            <section className={COL} aria-labelledby="contact-self">
              <h2 id="contact-self" className="m-0 font-mono text-[0.72rem] text-ink-mute">
                [ self-hosted ]
              </h2>
              <p className="m-0 font-mono text-[1.35rem] text-ink">Free</p>
              <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[0.8125rem] leading-[1.55] text-ink-soft">
                {CONTACT_SELF_FEATURES.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </section>
            <section className={COL} aria-labelledby="contact-managed">
              <h2 id="contact-managed" className="m-0 font-mono text-[0.72rem] text-ink-mute">
                [ managed ]
              </h2>
              <p className="m-0 font-mono text-[1.35rem] text-ink">Coming soon</p>
              <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[0.8125rem] leading-[1.55] text-ink-soft">
                {CONTACT_MANAGED_FEATURES.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              <ContactMailto
                email={MANAGED_CONTACT_EMAIL}
                subject={MANAGED_CONTACT_SUBJECT}
                className="mt-2 inline-flex h-auto items-center border border-hair px-4 py-[0.7rem] font-mono text-[0.8rem] text-ink no-underline hover:bg-surface-2"
              >
                Write to us
              </ContactMailto>
            </section>
          </div>
        </div>
      </DocumentFrame>
    </main>
  );
}
