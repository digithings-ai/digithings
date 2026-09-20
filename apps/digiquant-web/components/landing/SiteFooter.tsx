/**
 * SiteFooter — digiquant.io composition of the shared Footer + SocialRow
 * primitives (mirrors digithings-web's DtFooter). Utility links stay in
 * Footer; company profiles are the quiet icon row, not a Connect column — so
 * digiquant's footer single-sources through the kit instead of each page
 * assembling `<Footer links={DQ_FOOTER} …/>` inline. `meta` is overridable for
 * pages whose footer note differs (the tearsheet's "illustrative, in-sample").
 */
import { Footer, SocialRow } from "@digithings/ui";
import { DQ_FOOTER, DQ_FOOTER_META } from "@/app/_nav";

export function SiteFooter({ meta = DQ_FOOTER_META }: { meta?: string }) {
  return <Footer links={DQ_FOOTER} meta={meta} profiles={<SocialRow />} />;
}
