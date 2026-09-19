"use client";

import { DocsApp } from "./docs-app";
import { DocsConfigProvider } from "./config-provider";

export function WebpageAssistant() {
  return (
    <DocsConfigProvider>
      <DocsApp />
    </DocsConfigProvider>
  );
}
