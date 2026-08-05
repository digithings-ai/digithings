import type { Metadata } from "next";
import Link from "next/link";
import { Footer } from "@digithings/web";
import { DT_CONTACT_EMAIL, DT_FOOTER, DT_FOOTER_META } from "../../_nav";
import { PageHead } from "../../_company/prose";
import {
  DraftBanner,
  DraftFooterNote,
  DraftOutline,
  type DraftSection,
} from "../_draft";
import { DtNav } from "@/components/DtNav";

export const metadata: Metadata = {
  // Kept out of search results until real reviewed text lands. The visible
  // DraftBanner stops a *visitor* mistaking the outline for a policy, but a
  // search result for "digithings terms" that opens a draft misleads before the
  // banner is ever read — and the fix is one line, not a copy argument.
  robots: { index: false, follow: true },
  title: "terms of use — draft outline",
  description:
    "Draft outline of the DigiThings website and services terms of use. Not in force, not legal " +
    "advice, pending review by counsel.",
};

// /legal/terms — SKELETON. See ../_draft.tsx for why these are outlines and not
// text: NEEDS REAL COUNSEL. Nothing below is a term, a warranty, a liability
// cap, or an acceptance mechanism, and nothing below should be turned into one
// by an engineer. Each `note` names the subject matter of a missing clause; it
// never states what the clause will say.
//
// One structural point for whoever drafts this: the code is MIT-licensed and the
// LICENSE file already carries the software warranty disclaimer. These terms
// govern the *website and any services engagement*, which the licence does not
// touch. Conflating the two would either over-claim against the licence's
// permissions or leave the services relationship ungoverned.
const SECTIONS: DraftSection[] = [
  {
    heading: "Scope and acceptance",
    note: "What this document covers — the website, the documentation, and any hosted demo — and what falls outside it.",
  },
  {
    heading: "Definitions",
    note: "The terms used throughout, including what is meant by the software, the services, and a user.",
  },
  {
    heading: "Relationship to the software licence",
    note: "How these terms sit alongside the repository's MIT licence, which governs use of the code itself.",
  },
  {
    heading: "Permitted use of the website",
    note: "What visitors may do with the site and its documentation, and the conduct that is out of bounds.",
  },
  {
    heading: "Accounts and access",
    note: "Whether any part of the site requires an account, and the obligations attached if it does.",
  },
  {
    heading: "Services engagements",
    note: "How a paid engagement is formed, and the precedence between these terms and any signed statement of work.",
  },
  {
    heading: "Third-party services and provider keys",
    note: "The role of model providers and other third parties a self-hosted deployment connects to, and whose terms apply there.",
  },
  {
    heading: "Intellectual property",
    note: "Ownership of the site content, trade marks, and contributed material.",
  },
  {
    heading: "Warranties and disclaimers",
    note: "To be drafted by counsel. No warranty position is stated on this page in the interim.",
  },
  {
    heading: "Limitation of liability",
    note: "To be drafted by counsel. No cap, exclusion, or allocation of risk is stated on this page in the interim.",
  },
  {
    heading: "Indemnities",
    note: "Any indemnity obligations, in either direction, and their scope.",
  },
  {
    heading: "Term, suspension and termination",
    note: "How access may end, and what survives it.",
  },
  {
    heading: "Changes to these terms",
    note: "How revisions are made and how users are notified of them.",
  },
  {
    heading: "Governing law and disputes",
    note: "The governing law, the forum, and the process for resolving a dispute.",
  },
  {
    heading: "Contact",
    note: "Where to send notices and questions about this document.",
  },
];

export default function TermsPage() {
  return (
    <>
      <DtNav />

      <main className="pt-[var(--dq-nav-h)]">
        <PageHead kicker={"// legal · draft"} title="Terms of use">
          The outline of the terms that will govern this website and any services engagement. It is
          published in this state on purpose: the structure is useful to see, and a plausible-looking
          placeholder would be worse than a visible gap.
        </PageHead>

        <section className="section">
          <div className="wrap">
            <DraftBanner />
          </div>
        </section>

        <section className="section pt-0">
          <div className="wrap">
            <DraftOutline sections={SECTIONS} />
            <DraftFooterNote>
              Until this is finished, two things do apply and are not drafts. The code in the
              repository is licensed under MIT, whose text is the authoritative statement of what you
              may do with the software and of the warranty position on the code. And{" "}
              <Link className="text-accent [text-underline-offset:2px] hover:text-ink" href="/security">
                the security page
              </Link>{" "}
              describes the actual posture of the stack, including its documented limits. For anything
              else, ask:{" "}
              <a
                className="text-accent [text-underline-offset:2px] hover:text-ink"
                href={`mailto:${DT_CONTACT_EMAIL}?subject=DigiThings%20terms%20question`}
              >
                {DT_CONTACT_EMAIL}
              </a>
              .
            </DraftFooterNote>
          </div>
        </section>
      </main>

      <Footer links={DT_FOOTER} meta={DT_FOOTER_META} />
    </>
  );
}
