import { LayoutLines } from "@digithings/ui";
import { skinShowsSiteRails } from "@digithings/ui/chat/skins";

/**
 * The website's vertical rails (`LayoutLines`) on the product chat.
 * Framed modes (modal, sidebar, embed) do not mount them: the host page
 * owns its own frame, and a wide iframe would draw a second pair.
 * They are the house look: a known non-house skin never draws them. An
 * unresolved skin (the config is still loading) keeps the product default.
 */
export function SiteRails({ mode, skin }: { mode: string; skin?: string | null }) {
  if (mode !== "app") return null;
  if (skin != null && !skinShowsSiteRails(skin)) return null;
  return <LayoutLines className="site-rails" />;
}
