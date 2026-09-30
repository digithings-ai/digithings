import type { Metadata } from "next";
import { DocumentFrame, PageTitle } from "@digithings/ui";

export const metadata: Metadata = {
  title: "Contact — digiquant",
  description:
    "Self-host the full open-core stack for free, or have digiquant managed for you. What's included in each.",
};

export default function ContactPage() {
  return (
    <main id="main" tabIndex={-1}>
      <DocumentFrame>
        <PageTitle title="Contact">placeholder</PageTitle>
      </DocumentFrame>
    </main>
  );
}
