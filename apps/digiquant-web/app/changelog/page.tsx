import type { Metadata } from "next";
import { CtaLink, DocumentFrame, PageTitle } from "@digithings/ui";
import { TAGGED_RELEASES } from "@/lib/releases";

export const metadata: Metadata = {
  title: "changelog — tagged stack releases",
  description:
    "Tagged digichat and digiskills releases from the repository this desk is built on. The quant engine ships on develop without a product tag.",
};

export default function ChangelogPage() {
  return (
    <main id="main" tabIndex={-1}>
      <DocumentFrame>
        <div className="px-[var(--page-pad)] py-[var(--page-step)]">
          <PageTitle title="Changelog">
            Tagged digichat and digiskills releases from the repository. digiquant ships on develop and has no product tag on this page.
          </PageTitle>
          <ul className="m-0 mt-8 list-none border border-hair p-0">
            {TAGGED_RELEASES.map((release) => (
              <li key={`${release.product}-${release.version}`} className="border-b border-hair last:border-b-0">
                <CtaLink
                  href={release.href}
                  external
                  variant="ghost"
                  className="h-auto w-full items-baseline justify-between gap-3 px-4 py-3 text-start no-underline hover:bg-surface-2"
                >
                  <span className="font-mono text-[0.85rem] text-ink">
                    {release.product} {release.version}
                  </span>
                  <span className="font-mono text-[0.72rem] font-normal text-ink-mute">{release.date}</span>
                </CtaLink>
              </li>
            ))}
          </ul>
        </div>
      </DocumentFrame>
    </main>
  );
}
