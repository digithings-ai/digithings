import type { Metadata } from "next";
import Link from "next/link";
import { buttonVariants } from "@digithings/ui/ui";
import { SiteNav } from "@/components/landing/SiteNav";
import { SiteFooter } from "@/components/landing/SiteFooter";

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
          <header className="dq-sechead">
            <div className="kicker">{"// missing"}</div>
            <h1 className="dq-title">No such page.</h1>
            <p className="dq-sub">
              Nothing is filed under this address. The strategy library is the
              fastest way back.
            </p>
            <div className="flex flex-wrap gap-[0.8rem]">
              <Link className={buttonVariants({ variant: "default" })} href="/">
                Back to top
              </Link>
              <Link className={buttonVariants({ variant: "ghost" })} href="/strategies">
                Browse strategies
              </Link>
            </div>
          </header>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
