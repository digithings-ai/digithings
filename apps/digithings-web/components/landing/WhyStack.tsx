/**
 * The `#why` band (migrated, #4429).
 *
 * The app-first band: three example apps, each drawn as its digithings flow.
 * This component is a thin alias so `LandingPage` keeps rendering `<WhyStack />`
 * at the `#why` anchor.
 */

import { AppFirstSection } from "@/components/landing/AppFirstSection";

export function WhyStack() {
  return <AppFirstSection />;
}
