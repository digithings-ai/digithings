import { DocsApp } from "@/components/docs/docs-app";
import { DocsConfigProvider } from "@/lib/docs/config-provider";

export default function Home() {
  return (
    <DocsConfigProvider>
      <DocsApp />
    </DocsConfigProvider>
  );
}
