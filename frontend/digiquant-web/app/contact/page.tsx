import type { Metadata } from "next";
import { Footer, Reveal } from "@digithings/web";
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

            <div className="grid dq-contact" style={{ marginInline: "auto", marginTop: "2.4rem" }}>
              <Reveal className="price-card">
                <h3>Self hosted</h3>
                <p className="price">
                  open core · <span className="dq-up">free</span>
                </p>
                <ul>
                  {CONTACT_SELF_FEATURES.map((feature) => (
                    <li key={feature}>{feature}</li>
                  ))}
                </ul>
                <CloneRepoButton />
              </Reveal>

              <Reveal className="price-card accent">
                <h3>Managed</h3>
                <p className="price">contact us</p>
                <ul>
                  {CONTACT_MANAGED_FEATURES.map((feature) => (
                    <li key={feature}>{feature}</li>
                  ))}
                </ul>
                <a className="btn btn-primary" href={MANAGED_CONTACT_MAILTO}>
                  Email us <span aria-hidden="true">→</span>
                </a>
              </Reveal>
            </div>

            <Reveal>
              <p className="dq-built" style={{ textAlign: "center", marginTop: "2.4rem" }}>
                Not sure which fits? Start self-managed — it&rsquo;s the full product — and{" "}
                <a href={MANAGED_CONTACT_MAILTO}>get in touch</a> if you later want it managed.
              </p>
            </Reveal>
          </div>
        </section>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
