import type { Metadata } from "next";
import Link from "next/link";
import { Footer } from "@digithings/web";
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
      <main className="dq-subpage">
        <div className="wrap pb-[clamp(4.5rem,10vw,7rem)]">
          <header className="dq-sechead">
            <div className="kicker">{"// missing"}</div>
            <h1 className="dq-title">No such page.</h1>
            <p className="dq-sub">
              Nothing is filed under this address. The strategy library is the
              fastest way back.
            </p>
            <div className="flex flex-wrap gap-[0.8rem]">
              <Link className="btn btn-primary" href="/">
                Back to top
              </Link>
              <Link className="btn btn-ghost" href="/strategies">
                Browse strategies
              </Link>
            </div>
          </header>
        </div>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
