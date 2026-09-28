/**
 * The `#why` band (migrated, #4429).
 *
 * The app-first variant won the `/variants/why-copy` review: three apps,
 * each with its own provider architecture, a scroll-driven walk, a morph
 * that swaps the stack to digithings box by box, and a sticky invoice that
 * stays live throughout. This component is a thin alias so `LandingPage`
 * keeps rendering `<WhyStack />` at the `#why` anchor untouched.
 *
 * The old rented-then-owned walk (`@/lib/whyStack`) is retired but left on
 * disk until the `/variants/why-copy` review page is removed.
 */

import { AppFirstSection } from "@/components/landing/AppFirstSection";

export function WhyStack() {
  return <AppFirstSection />;
}
