import type { Metadata } from "next";
import Link from "next/link";
import { DtNav } from "@/components/DtNav";
import { DtFooter } from "@/components/DtFooter";
import { PageHead } from "./_company/prose";

export const metadata: Metadata = {
  title: "No such page — digithings",
  description: "The address does not match anything on digithings.ai.",
};

export default function NotFound() {
  return (
    <>
      <DtNav />
      <main className="pt-[var(--dq-nav-h)]">
        <PageHead kicker="// 404" title="No such page.">
          The address does not match anything on this site. The docs index is the
          fastest way back.
        </PageHead>
        <section className="section">
          <div className="wrap">
            <div className="flex flex-wrap gap-[0.8rem]">
              <Link className="btn btn-primary" href="/">
                Back to top
              </Link>
              <Link className="btn btn-ghost" href="/docs">
                Browse the docs
              </Link>
            </div>
          </div>
        </section>
      </main>
      <DtFooter />
    </>
  );
}
