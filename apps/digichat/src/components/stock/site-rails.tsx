import { LayoutLines } from "@digithings/ui";

/**
 * The website's vertical rails (`LayoutLines`) on the product chat.
 * Framed modes (modal, sidebar, embed) do not mount them: the host page
 * owns its own frame, and a wide iframe would draw a second pair.
 */
export function SiteRails({ mode }: { mode: string }) {
  if (mode !== "app") return null;
  return <LayoutLines className="site-rails" />;
}
