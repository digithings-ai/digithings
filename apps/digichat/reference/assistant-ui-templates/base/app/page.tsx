import { DemoRuntimeProvider } from "@/components/runtime/demo-runtime-provider";
import { Base } from "@/components/examples/base";

export default function Page() {
  return (
    <main className="h-dvh overflow-hidden">
      <DemoRuntimeProvider>
        <Base />
      </DemoRuntimeProvider>
    </main>
  );
}
