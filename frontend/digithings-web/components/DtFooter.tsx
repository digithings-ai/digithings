/**
 * DtFooter — digithings.ai composition of the shared Footer + SocialRow
 * primitives. Utility links stay in Footer; company profiles are the quiet
 * icon row, not a Connect column.
 */
import { Footer, SocialRow } from "@digithings/web";
import { DT_FOOTER, DT_FOOTER_META } from "@/app/_nav";

export function DtFooter() {
  return <Footer links={DT_FOOTER} meta={DT_FOOTER_META} profiles={<SocialRow />} />;
}
