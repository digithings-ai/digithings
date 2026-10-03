"use client";

import { useEffect } from "react";
import Link from "next/link";
import { SiteNav } from "@/components/landing/SiteNav";
import { Footer } from "@digithings/ui";
import { DQ_FOOTER, DQ_FOOTER_META } from "../_nav";

// Retired standalone page — method content lives at /#method on the homepage.
export default function PipelineRedirect() {
  useEffect(() => {
    window.location.replace("/#method");
  }, []);

  return (
    <>
      <SiteNav />
      <main className="section dq-subpage" id="main" tabIndex={-1}>
        <p className="text-center text-ink-soft">
          Redirecting… <Link href="/#method">Continue to method</Link>
        </p>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
