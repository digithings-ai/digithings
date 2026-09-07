import { Assistant } from "@/app/assistant";
import { ProductDashboard } from "@/components/support/product-dashboard";
import { SupportConfigProvider } from "@/lib/support/config-provider";

export function SupportApp() {
  return (
    <SupportConfigProvider>
      <ProductDashboard />
      <Assistant />
    </SupportConfigProvider>
  );
}
