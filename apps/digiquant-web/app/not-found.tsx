import type { Metadata } from "next";
import Link from "next/link";
import { CtaLink, Footer } from "@digithings/ui";
import { DQ_FOOTER, DQ_FOOTER_META } from "./_nav";
import { SiteNav } from "@/components/landing/SiteNav";

export const metadata: Metadata = {
  title: "No such page — digiquant",
  description: "The address does not match anything on digiquant.io.",
};

export default function NotFound() {
  return (
    <>
      <SiteNav />
      <main className="dq-subpage" id="main" tabIndex={-1}>
        <div className="wrap pb-[clamp(4.5rem,10vw,7rem)]">
          <header className="section-head">
            <div className="kicker">{"// missing"}</div>
            <h1 className="dq-title">No such page.</h1>
            <p className="dq-sub">Nothing is filed under this address.</p>
            <div className="mt-[1.4rem] flex flex-wrap gap-[0.8rem]">
              <CtaLink href="/" variant="default">
                Back to the desk
              </CtaLink>
              <Link className="font-mono text-[0.88rem] text-ink-mute" href="/#watch">
                Watch
              </Link>
            </div>
          </header>
        </div>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
