import type { Metadata } from "next";
import { DocumentFrame, PageTitle } from "@digithings/ui";

export const metadata: Metadata = {
  title: "changelog — tagged stack releases",
  description:
    "Tagged digichat and digiskills releases from the repository this desk is built on. The quant engine ships on develop without a product tag.",
};

export default function ChangelogPage() {
  return (
    <main id="main" tabIndex={-1}>
      <DocumentFrame>
        <PageTitle title="Changelog">placeholder</PageTitle>
      </DocumentFrame>
    </main>
  );
}
