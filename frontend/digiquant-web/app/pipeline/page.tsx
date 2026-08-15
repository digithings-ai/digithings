"use client";

import { useEffect } from "react";
import Link from "next/link";
import { SiteNav } from "@/components/landing/SiteNav";
import { Footer } from "@digithings/web";
import { DQ_FOOTER, DQ_FOOTER_META } from "../_nav";

// Retired standalone page — pipeline content lives at /#pipeline on the homepage.
export default function PipelineRedirect() {
  useEffect(() => {
    window.location.replace("/#pipeline");
  }, []);

  return (
    <>
      <SiteNav />
      <main className="section dq-subpage" style={{ minHeight: "50vh", display: "grid", placeItems: "center" }}>
        <p style={{ color: "var(--ink-soft)" }}>
          Redirecting… <Link href="/#pipeline">Continue to pipeline</Link>
        </p>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
