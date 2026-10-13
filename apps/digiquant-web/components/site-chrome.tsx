"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { NavShell } from "@digithings/ui";
import { Footer } from "@/app/_chrome/Footer";
import { LayoutRails } from "@/app/_chrome/LayoutRails";
import { SectionRail } from "@/app/_chrome/SectionRail";
import { isDeskPath } from "@/components/desk/paths";
import { Brand, DQ_NAV_PRIMARY } from "@/app/_nav";

/** Marketing chrome stays off the terminal so /app is the desk, not a second homepage. */
export function SiteChrome({ children }: { children: ReactNode }) {
  const path = usePathname() ?? "/";
  if (isDeskPath(path)) return children;
  return (
    <>
      <NavShell brand={<Brand />} links={DQ_NAV_PRIMARY} homeLabel="digiquant home" skipTo="#main" showThemeToggle={false} />
      <LayoutRails />
      <SectionRail />
      <div className="pt-[var(--nav-shell-h,62px)]">{children}</div>
      <Footer />
    </>
  );
}
