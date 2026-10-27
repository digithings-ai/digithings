import { BrandWordmark } from "@digithings/ui";

/** The closing mark above the footer. Same studio wordmark as the hero, at page width. */
export function FooterWordmark() {
  return (
    <div className="pixel-word-band">
      <BrandWordmark className="pixel-word pixel-word-footer" />
    </div>
  );
}
