import type { Metadata } from "next";
import Link from "next/link";
import { Footer, Reveal } from "@digithings/web";
import { DT_CONTACT_EMAIL, DT_FOOTER, DT_FOOTER_META } from "../_nav";
import { PageHead, RuledList, RuledRow } from "../_company/prose";
import { DtNav } from "@/components/DtNav";

export const metadata: Metadata = {
  title: "services — advisory, implementation, and support",
  description:
    "The stack is MIT-licensed and free to self-host. We also work directly with teams: " +
    "architecture advisory, integration builds on top of DigiThings, and retained support for " +
    "teams running it in production.",
};

// /services — the commercial surface. Structured as three named engagements so
// each one names a buyer, in the spirit of how NautilusTrader tiers its
// Open Source / Pro / Cloud / Institutional lines: the difference between the
// tiers is who is asking, not a feature matrix.
//
// >>> OWNER TO CONFIRM — everything in ENGAGEMENTS and PROCESS below is
// >>> PLACEHOLDER SCOPE. The brief supplied one sentence of substance ("he and
// >>> his team provide services to integrate this infrastructure and build
// >>> applications on it"); the three engagement names, their audiences and
// >>> their bullet lists are a reasonable decomposition of that sentence, not
// >>> an offering anyone has signed off. Read each `for` and `includes` line as
// >>> a proposal.
//
// Deliberately absent, and it should stay that way until the owner says
// otherwise:
//   * NO PRICING, no day rates, no retainer bands, no "from $X".
//   * NO response-time or availability commitments — an SLA on a public page is
//     a contractual term, and there is no SLA to describe.
//   * NO client names, logos, case studies or testimonials. There is no
//     evidence for any in this repository, so inventing social proof was never
//     an option.
//   * NO team size or named staff beyond /team's single confirmed entry.

type Engagement = {
  num: string;
  name: string;
  tier: string;
  /** Who is asking. One sentence, buyer-side. */
  audience: string;
  summary: string;
  includes: string[];
};

const ENGAGEMENTS: Engagement[] = [
  {
    num: "01",
    name: "Advisory",
    tier: "assess",
    audience:
      "For a team that has decided to run its own agent infrastructure and needs to know whether " +
      "this one fits before committing engineering time to it.",
    summary:
      "A short, bounded engagement that ends in a written recommendation rather than a codebase. " +
      "We read your existing stack, map it against the modules, and say plainly where DigiThings " +
      "helps and where it does not.",
    includes: [
      "Architecture review against your current orchestration, data and model-provider setup",
      "A module-by-module fit assessment — what you would adopt, what you would skip",
      "A deployment and security walkthrough for your environment, using the published threat model",
      "A written recommendation, including the case for not adopting it",
    ],
  },
  {
    num: "02",
    name: "Implementation",
    tier: "build",
    audience:
      "For a team that wants the stack wired into what they already run, or an application built " +
      "on top of it, and would rather not spend a quarter learning the internals first.",
    summary:
      "Hands-on delivery. We stand the stack up in your environment, connect it to your identity " +
      "provider, your data and your provider keys, and build the modules or the application layer " +
      "you actually need on top.",
    includes: [
      "Self-hosted deployment in your environment — your hardware, your network, your keys",
      "Integration with your identity provider, data stores and existing services",
      "New modules, agents, tools or an application layer built to the same rubrics as the core",
      "Handover: architecture documentation, tests, and the CI wiring to keep it green",
    ],
  },
  {
    num: "03",
    name: "Ongoing support",
    tier: "run",
    audience:
      "For a team already running DigiThings in production that wants someone accountable for " +
      "upgrades and a direct line when something is unclear.",
    summary:
      "A continuing relationship rather than a project. The point is that upgrades stop being a " +
      "research task and that your questions reach the people who wrote the code.",
    includes: [
      "Upgrade planning and assistance as the stack moves — including breaking-change guidance",
      "A direct channel for questions and triage",
      "Review of changes your team makes against the same security and quality rubrics",
      "Input into the roadmap, so the work you depend on is work we know about",
    ],
  },
];

// How an engagement starts. Process, not commercial terms.
const PROCESS: { term: string; body: string }[] = [
  {
    term: "A conversation first",
    body:
      "Tell us what you are running and what you are trying to build. If the honest answer is that " +
      "you should self-host the stack from the repository and not pay anyone, that is the answer " +
      "you will get — the software is MIT and it does not need us to be useful.",
  },
  {
    term: "A written scope",
    body:
      "Anything we take on is scoped in writing before it starts: what is being delivered, what is " +
      "explicitly out of scope, and what we need from your side to proceed.",
  },
  {
    term: "Your infrastructure, your keys",
    body:
      "Engagements run against infrastructure you own, with provider credentials that stay yours. " +
      "There is no hosted tier to migrate onto and no lock-in created by working with us.",
  },
  {
    term: "Everything general goes upstream",
    body:
      "Improvements that are not specific to your deployment land in the public repository under " +
      "MIT. You keep what is yours; the stack gets better for everyone else.",
  },
];

export default function ServicesPage() {
  return (
    <>
      <DtNav />

      <main className="pt-[var(--dq-nav-h)]">
        <PageHead
          kicker={"// services"}
          title={
            <>
              The software is free. <em>Time is not.</em>
            </>
          }
        >
          Everything on this site is MIT-licensed and self-hostable without talking to us, and most
          teams should start exactly there. What we sell is the work around it: deciding whether it
          fits, wiring it into a stack that already exists, and staying available once it is running.
        </PageHead>

        <section className="section">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// three engagements"}</span>
              <h2>Named by who is asking.</h2>
              <p>
                Not a feature matrix — the modules are identical in all three. What differs is
                whether you need a decision, a build, or a continuing relationship.
              </p>
            </Reveal>
            <div className="grid gap-[1.1rem] md:grid-cols-3">
              {ENGAGEMENTS.map((e) => (
                <Reveal key={e.name} className="mod-card">
                  <div className="mod-card-top">
                    <span className="font-mono text-[0.72rem] tracking-[0.14em] text-ink-mute">
                      {e.num}
                    </span>
                    <span className="dg-tier">{e.tier}</span>
                  </div>
                  <h3>{e.name}</h3>
                  <p className="mt-[0.4rem] text-[0.86rem] leading-[1.6] text-ink-mute">
                    {e.audience}
                  </p>
                  <p className="mt-[0.7rem] text-[0.92rem] leading-[1.65] text-ink-soft">
                    {e.summary}
                  </p>
                  <ul className="mt-[0.9rem] grid list-none gap-[0.5rem] p-0">
                    {e.includes.map((line) => (
                      <li
                        key={line}
                        className="grid grid-cols-[1rem_1fr] gap-[0.5rem] text-[0.86rem] leading-[1.6] text-ink-soft"
                      >
                        <span aria-hidden="true" className="font-mono text-accent">
                          ›
                        </span>
                        <span>{line}</span>
                      </li>
                    ))}
                  </ul>
                </Reveal>
              ))}
            </div>
            <p className="mt-[1.8rem] max-w-[64ch] text-[0.95rem] leading-[1.7] text-ink-soft">
              There is no pricing on this page because there is no standard shape to price. Scope
              comes first and the number follows it.
            </p>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// how it works"}</span>
              <h2>Four things that hold for all three.</h2>
            </Reveal>
            <RuledList>
              {PROCESS.map((p) => (
                <RuledRow key={p.term} term={p.term}>
                  {p.body}
                </RuledRow>
              ))}
            </RuledList>
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// start here"}</span>
              <h2>Tell us what you are building.</h2>
              <p>
                One email with your stack and your goal is enough to work out which of the three
                this is — or whether it is none of them.
              </p>
            </Reveal>
            <div className="flex flex-wrap gap-[0.8rem]">
              <a
                className="btn btn-primary"
                href={`mailto:${DT_CONTACT_EMAIL}?subject=DigiThings%20services%20inquiry`}
              >
                Email us <span aria-hidden="true">→</span>
              </a>
              <Link className="btn btn-ghost" href="/docs">
                Read the docs first
              </Link>
              <Link className="btn btn-ghost" href="/security">
                Security posture
              </Link>
            </div>
            <p className="mt-[1.4rem] font-mono text-[0.88rem] text-ink-mute">
              <a
                className="text-accent [text-underline-offset:2px] hover:text-ink"
                href={`mailto:${DT_CONTACT_EMAIL}`}
              >
                {DT_CONTACT_EMAIL}
              </a>
            </p>
          </div>
        </section>
      </main>

      <Footer links={DT_FOOTER} meta={DT_FOOTER_META} />
    </>
  );
}
