"use client";

import { useEffect } from "react";
import { DocumentFrame, PageTitle } from "@digithings/ui";

// Retired standalone page — pipeline content lives at /#pipeline on the homepage.
export default function PipelineRedirect() {
  useEffect(() => {
    window.location.replace("/#pipeline");
  }, []);

  return (
    <main id="main" tabIndex={-1}>
      <DocumentFrame>
        <PageTitle title="Pipeline">
          Redirecting to <a href="/#pipeline">/#pipeline</a>…
        </PageTitle>
      </DocumentFrame>
    </main>
  );
}
