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
  title: "privacy — draft outline",
  description:
    "Draft outline of the DigiThings privacy notice. Not in force, not legal advice, pending " +
    "review by counsel.",
};

// /legal/privacy — SKELETON. See ../_draft.tsx: NEEDS REAL COUNSEL.
//
// A privacy notice makes representations about processing, and a wrong
// representation is a regulatory exposure, so nothing here states what is
// collected, why, on what basis, or for how long. Each `note` names the subject
// matter of a missing section only.
//
// The distinction that whoever drafts this must get right — and that engineers
// should NOT pre-empt in copy — is between:
//   (a) this website, a static export with its own request logs and whatever the
//       hosting edge records; and
//   (b) a self-hosted deployment of the stack, which runs on the operator's own
//       infrastructure with the operator's own provider keys. In that case the
//       operator is the controller and we are not in the data path at all.
// Stating that split loosely would be worse than leaving it to counsel, so the
// outline only marks it as a section that must exist.
const SECTIONS: DraftSection[] = [
  {
    heading: "Who is responsible",
    note: "The identity and contact details of the controller for this website, and the legal entity behind it.",
  },
  {
    heading: "Scope: website versus self-hosted deployments",
    note: "The boundary between this website and a deployment of the software running on someone else's infrastructure, and who is responsible in each case.",
  },
  {
    heading: "What the website collects",
    note: "The categories of data the site and its hosting layer receive, and how they arise.",
  },
  {
    heading: "Why, and on what basis",
    note: "The purposes of processing and the lawful basis relied on for each.",
  },
  {
    heading: "Cookies and similar technologies",
    note: "Any cookies, local storage, or analytics the site uses, and how a visitor can control them.",
  },
  {
    heading: "Provider keys and prompt content",
    note: "How model-provider credentials and the content sent to providers are handled, and by whom.",
  },
  {
    heading: "Processors and sub-processors",
    note: "The third parties involved in operating the site and the services, and their role.",
  },
  {
    heading: "International transfers",
    note: "Where data is processed and the mechanism relied on for any transfer out of its origin jurisdiction.",
  },
  {
    heading: "Retention",
    note: "How long each category of data is kept, and what determines that period.",
  },
  {
    heading: "Your rights",
    note: "The rights available to individuals and the process for exercising them, including how to complain.",
  },
  {
    heading: "Security",
    note: "The technical and organisational measures relevant to the data described above.",
  },
  {
    heading: "Children",
    note: "The position on use by minors.",
  },
  {
    heading: "Changes to this notice",
    note: "How revisions are made and how they are communicated.",
  },
  {
    heading: "Contact",
    note: "Where to send privacy questions and formal requests.",
  },
];

export default function PrivacyPage() {
  return (
    <>
      <DtNav />

      <main className="pt-[var(--dq-nav-h)]">
        <PageHead kicker={"// legal · draft"} title="Privacy">
          The outline of a privacy notice for this website. A notice makes binding representations
          about how data is handled, so this one stays an outline until counsel has written it rather
          than borrowing language that sounds right.
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
              One thing worth saying plainly while the rest is drafted, because it is an
              architectural fact rather than a policy commitment: the stack is built to be
              self-hosted, and a deployment you run sits on your infrastructure with your provider
              keys. In that arrangement the data path does not pass through us.{" "}
              <Link className="text-accent [text-underline-offset:2px] hover:text-ink" href="/about">
                What the software is
              </Link>{" "}
              and{" "}
              <Link
                className="text-accent [text-underline-offset:2px] hover:text-ink"
                href="/security"
              >
                how it handles credentials and audit data
              </Link>{" "}
              are both documented. For a question this outline cannot answer, ask:{" "}
              <a
                className="text-accent [text-underline-offset:2px] hover:text-ink"
                href={`mailto:${DT_CONTACT_EMAIL}?subject=DigiThings%20privacy%20question`}
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
