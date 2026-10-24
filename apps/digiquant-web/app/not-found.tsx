import type { Metadata } from "next";
import { DocumentFrame, PageTitle } from "@digithings/ui";

export const metadata: Metadata = {
  title: "No such page — digiquant",
  description: "The address does not match anything on digiquant.io.",
};

export default function NotFound() {
  return (
    <main id="main" tabIndex={-1}>
      <DocumentFrame>
        <PageTitle title="No such page">Nothing is filed under this address.</PageTitle>
      </DocumentFrame>
    </main>
  );
}
