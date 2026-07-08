import type { Metadata } from "next";
import { Footer, PricingTierCard, Reveal } from "@digithings/web";
import { DQ_FOOTER, DQ_FOOTER_META } from "../_nav";
import {
  CONTACT_MANAGED_FEATURES,
  CONTACT_SELF_FEATURES,
  MANAGED_CONTACT_MAILTO,
} from "../_contact";
import { SiteNav } from "@/components/landing/SiteNav";
import { AmbientMesh } from "@/components/landing/AmbientMesh";
import { CloneRepoButton } from "@/components/landing/CloneRepoButton";

export const metadata: Metadata = {
  title: "Contact — digiquant",
  description:
    "Self-host the full open-core stack for free, or have Olympus managed for you. What's included in each.",
};

export default function ContactPage() {
  return (
    <>
      <SiteNav />
      <main className="dq-subpage">
        <AmbientMesh />
        <section className="section">
          <div className="wrap">
            <Reveal>
              <div style={{ textAlign: "center" }}>
                <span className="kicker">{"// contact"}</span>
                <h2 className="dq-title" style={{ marginInline: "auto" }}>
                  Own it, or have it run for you.
                </h2>
                <p className="dq-sub" style={{ marginInline: "auto" }}>
                  digiquant is open core. Self-manage the whole stack at no cost, or let us
                  manage Olympus for you. Same engine either way — the difference is who keeps
                  it running.
                </p>
              </div>
            </Reveal>

            {/* Two-tier cards: the shared PricingTierCard (hero voice, #1417) —
                ✓ feature grammar and the featured tier's flat accent wash come
                from @digithings/web pricing.css, so contact and the homepage
                pricing section speak one grammar. The app owns the grid. */}
            <div className="mx-auto mt-[2.4rem] grid max-w-[880px] grid-cols-2 gap-[1.25rem] max-[640px]:grid-cols-1">
              <Reveal>
                <PricingTierCard
                  variant="hero"
                  nameAs="h3"
                  className="h-full"
                  name="Self hosted"
                  priceLine={
                    <>
                      open core · <span className="text-up">free</span>
                    </>
                  }
                  features={[...CONTACT_SELF_FEATURES]}
                  cta={<CloneRepoButton />}
                />
              </Reveal>

              <Reveal>
                <PricingTierCard
                  variant="hero"
                  nameAs="h3"
                  className="h-full"
                  accent
                  name="Managed"
                  priceLine="contact us"
                  features={[...CONTACT_MANAGED_FEATURES]}
                  cta={
                    <a className="btn btn-primary" href={MANAGED_CONTACT_MAILTO}>
                      Email us <span aria-hidden="true">→</span>
                    </a>
                  }
                />
              </Reveal>
            </div>

            <Reveal>
              <p className="mx-auto mt-[2.4rem] max-w-[52ch] text-center text-[0.9rem] text-ink-mute">
                Not sure which fits? Start self-managed — it&rsquo;s the full product — and{" "}
                <a className="text-accent" href={MANAGED_CONTACT_MAILTO}>
                  get in touch
                </a>{" "}
                if you later want it managed.
              </p>
            </Reveal>
          </div>
        </section>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
