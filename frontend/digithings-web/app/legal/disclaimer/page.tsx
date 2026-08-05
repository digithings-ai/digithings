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
  title: "disclaimer — draft outline",
  description:
    "Draft outline of the DigiThings disclaimer, covering the software, the documentation, and " +
    "the quant research modules. Not in force, not legal advice, pending review by counsel.",
};

// /legal/disclaimer — SKELETON, and the one that most needs counsel.
//
// This repository ships digiquant: NautilusTrader-backed backtesting,
// optimisation, and (behind a human gate) live-trading code paths. A disclaimer
// that is merely plausible here is a liability rather than a copy defect —
// financial-disclaimer language is jurisdiction-specific, interacts with
// investment-advice and marketing rules, and can create the very exposure it is
// meant to limit if it is drafted by the wrong person. So: NO disclaimer text is
// asserted on this page. Every entry below names the subject matter of a clause
// that counsel must write.
//
// The only substantive statements permitted on this page are verifiable facts
// about the code, kept visually separate from the outline and labelled as facts
// rather than as disclaimers. They are true at the time of writing and checkable:
//   * digiquant/src/digiquant/brokers/stubs.py — the IB, Alpaca and QuantConnect
//     adapters raise NotImplementedError on connect() and submit_order().
//   * SECURITY.md documents the live-trading gate as source-tree plus a
//     commit-trailer enforced by a local pre-push hook — not a runtime interlock.
// If either fact changes, this page must change with it. /security carries the
// same statements with their limits spelled out.
const SECTIONS: DraftSection[] = [
  {
    heading: "Scope of this disclaimer",
    note: "Which materials it covers — the website, the documentation, the software, and any output the software produces.",
  },
  {
    heading: "No investment or financial advice",
    note: "The position on whether anything published here or produced by the software constitutes advice or a recommendation.",
  },
  {
    heading: "No offer or solicitation",
    note: "Whether any material here constitutes an offer, a solicitation, or the marketing of a financial product.",
  },
  {
    heading: "Backtested and simulated results",
    note: "The treatment of historical, backtested, and optimised results, and their relationship to real outcomes.",
  },
  {
    heading: "Trading and execution risk",
    note: "The risks attaching to any use of the quant modules in connection with real markets, and where responsibility sits.",
  },
  {
    heading: "Software warranty position",
    note: "How the disclaimer relates to the warranty terms already stated in the repository's MIT licence, without duplicating or contradicting them.",
  },
  {
    heading: "Model output and AI-generated content",
    note: "The treatment of output produced by language models running inside the stack, including its accuracy and suitability.",
  },
  {
    heading: "Accuracy of documentation and data",
    note: "The position on errors in the documentation and on data supplied by upstream sources.",
  },
  {
    heading: "Third-party providers and market data",
    note: "The role of model providers, data vendors and brokers a deployment connects to, and whose terms govern them.",
  },
  {
    heading: "No professional relationship",
    note: "Whether reading this site or using the software creates any advisory, fiduciary, or professional relationship.",
  },
  {
    heading: "Regulatory status and jurisdiction",
    note: "The regulatory position of the entity behind the software, and the jurisdictions the disclaimer is written for.",
  },
  {
    heading: "Contact",
    note: "Where to raise a question about anything in this document.",
  },
];

export default function DisclaimerPage() {
  return (
    <>
      <DtNav />

      <main className="pt-[var(--dq-nav-h)]">
        <PageHead kicker={"// legal · draft"} title="Disclaimer">
          The outline of a disclaimer covering this website, the software, and the quant research
          modules. This is the page it would be most tempting to fill with borrowed boilerplate, and
          the one where borrowed boilerplate would do the most damage.
        </PageHead>

        <section className="section">
          <div className="wrap">
            <DraftBanner />
          </div>
        </section>

        <section className="section pt-0">
          <div className="wrap">
            <DraftOutline sections={SECTIONS} />

            {/* Facts about the code, deliberately fenced off from the outline
                above and labelled as facts. These are checkable in the
                repository; they are not, and must not be read as, a disclaimer
                of anything. */}
            <div className="mt-[2.4rem] max-w-[70ch] border-t border-hair pt-[1.6rem]">
              <span className="block font-mono text-[0.7rem] uppercase tracking-[0.14em] text-ink-mute">
                Facts about the code, not a disclaimer
              </span>
              <p className="mt-[0.7rem] text-[0.92rem] leading-[1.7] text-ink-soft">
                Two things are worth stating while the document above is written, because they are
                properties of the source rather than legal positions. The broker adapters for
                Interactive Brokers, Alpaca and QuantConnect exist as stubs whose connect and
                order-submission methods raise <code className="font-mono text-[0.92em] text-ink">NotImplementedError</code>
                , so the stack as published does not place orders anywhere. And the control that keeps
                it that way is a review gate — a source-tree fact plus a required human co-sign on
                commits touching those paths — not a runtime interlock in a running system.
              </p>
              <p className="mt-[0.8rem] text-[0.92rem] leading-[1.7] text-ink-soft">
                Both statements, with their limits spelled out rather than summarised, are on{" "}
                <Link
                  className="text-accent [text-underline-offset:2px] hover:text-ink"
                  href="/security"
                >
                  the security page
                </Link>
                . Anyone who wires a real adapter into their own deployment has changed those facts
                for themselves, and nothing here speaks to that deployment.
              </p>
            </div>

            <DraftFooterNote>
              For the warranty position on the code itself, the repository&rsquo;s MIT licence is the
              authoritative text and is in force today. For anything this outline does not answer,
              ask rather than infer:{" "}
              <a
                className="text-accent [text-underline-offset:2px] hover:text-ink"
                href={`mailto:${DT_CONTACT_EMAIL}?subject=DigiThings%20disclaimer%20question`}
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
