import "./home.css";
import { ButtonsCtaReference } from "@/components/buttons-cta-reference";
import { ContentsOverview } from "@/components/contents-overview";
import { FeaturePickerReference } from "@/components/feature-picker-reference";
import { LiverySwitcher } from "@/components/livery-switcher";
import { ThemeGallery } from "@/components/theme-gallery-reference";

export default function FoundationsPage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// frontend design reference"}</p>
        <h1>
          Utilitarian terminal <em>baseline</em>.
        </h1>
        <p>
          Shared source for every live surface. Products import{" "}
          <code>@digithings/web</code> and <code>@digithings/design</code> — they do not restyle
          in parallel. Each page in the top bar is one family.
        </p>
      </header>

      <ContentsOverview />
      <ThemeGallery />
      <LiverySwitcher />
      <FeaturePickerReference />
      <ButtonsCtaReference />
    </main>
  );
}
