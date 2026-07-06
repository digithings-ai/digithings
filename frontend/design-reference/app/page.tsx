import "./home.css";
import { ButtonsCtaReference } from "@/components/buttons-cta-reference";
import { ContentsOverview } from "@/components/contents-overview";
import { FeaturePickerReference } from "@/components/feature-picker-reference";
import { LiverySwitcher } from "@/components/livery-switcher";

export default function FoundationsPage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// frontend design reference"}</p>
        <h1>
          React <em>+ Tailwind + Motion</em> baseline.
        </h1>
        <p>
          Consolidated, app-native reference surface for frontend sections before migration into
          digithings-web, digiquant-web, and digichat. Each page in the top bar holds one family
          of design elements.
        </p>
      </header>

      <ContentsOverview />
      <LiverySwitcher />
      <FeaturePickerReference />
      <ButtonsCtaReference />
    </main>
  );
}
