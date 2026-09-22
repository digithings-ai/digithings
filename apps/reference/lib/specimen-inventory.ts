/**
 * The canon's route and specimen inventory.
 *
 * This is the machine-readable form of the IA: every gallery route declared
 * once, and every `@digithings/ui/ui` module mapped to the single specimen file
 * that is its canonical home. `lib/*.test.ts` pins both against the filesystem
 * and against `packages/ui/src/ui/index.ts`, so a moved route, a renamed
 * specimen, or a new kit part cannot drift silently.
 */

export type RouteEntry = {
  /** The URL as served (no trailing slash). */
  route: string;
  /** Family folder under `app/(gallery)` (or `(chatbot)` for the chat shell). */
  group: string;
  /** Repo-relative path to the route's `page.tsx`. */
  page: string;
};

export const ROUTES: readonly RouteEntry[] = [
  { route: "/", group: "foundations", page: "app/(gallery)/(foundations)/page.tsx" },
  { route: "/rtl", group: "rtl", page: "app/(gallery)/rtl/page.tsx" },
  { route: "/typography", group: "typography", page: "app/(gallery)/(typography)/typography/page.tsx" },
  { route: "/controls", group: "controls", page: "app/(gallery)/(controls)/controls/page.tsx" },
  { route: "/data", group: "data-display", page: "app/(gallery)/(data-display)/data/page.tsx" },
  { route: "/finance", group: "finance", page: "app/(gallery)/(finance)/finance/page.tsx" },
  { route: "/effects", group: "motion", page: "app/(gallery)/(motion)/effects/page.tsx" },
  { route: "/chrome", group: "chrome", page: "app/(gallery)/(chrome)/chrome/page.tsx" },
  { route: "/terminal", group: "chat", page: "app/(gallery)/(chat)/terminal/page.tsx" },
  { route: "/layout-patterns", group: "layout", page: "app/(gallery)/(layout)/layout-patterns/page.tsx" },
  { route: "/symbols", group: "symbols", page: "app/(gallery)/(symbols)/symbols/page.tsx" },
  { route: "/account", group: "pages/templates", page: "app/(gallery)/(pages)/(templates)/account/page.tsx" },
  { route: "/brand", group: "lab", page: "app/(gallery)/(lab)/brand/page.tsx" },
  { route: "/iterate", group: "lab", page: "app/(gallery)/(lab)/iterate/page.tsx" },
  { route: "/chatbot", group: "chat", page: "app/(chatbot)/chatbot/page.tsx" },
] as const;

export type SpecimenEntry = {
  /** The canonical home component for this kit part. */
  specimen: string;
  /** The route that renders it. */
  route: string;
  /** A component name the specimen file must reference, where one names the part. */
  marker?: string;
};

/**
 * Canonical specimen home per `packages/ui/src/ui` module. Keys mirror the
 * `export * from "./<key>"` lines in `packages/ui/src/ui/index.ts`; a new kit
 * module with no entry here fails the specimen contract test.
 */
export const SPECIMENS: Readonly<Record<string, SpecimenEntry>> = {
  alert: { specimen: "components/controls/kit-surface-reference.tsx", route: "/controls", marker: "Alert" },
  avatar: { specimen: "components/brand/avatar-kit-reference.tsx", route: "/brand", marker: "Avatar" },
  badge: { specimen: "components/controls/kit-surface-reference.tsx", route: "/controls", marker: "Badge" },
  breadcrumb: { specimen: "components/chrome/breadcrumbs-reference.tsx", route: "/chrome", marker: "Breadcrumbs" },
  button: { specimen: "components/controls/kit-surface-reference.tsx", route: "/controls", marker: "Button" },
  card: { specimen: "components/controls/kit-surface-reference.tsx", route: "/controls", marker: "Card" },
  checkbox: { specimen: "components/controls/form-fields-reference.tsx", route: "/controls", marker: "Checkbox" },
  collapsible: { specimen: "components/controls/accordion-reference.tsx", route: "/controls", marker: "Collapsible" },
  "date-pager": { specimen: "components/controls/nav-buttons-reference.tsx", route: "/controls", marker: "DatePager" },
  dialog: { specimen: "components/controls/dialog-reference.tsx", route: "/controls", marker: "Dialog" },
  "dropdown-menu": { specimen: "components/controls/dropdown-reference.tsx", route: "/controls", marker: "DropdownMenu" },
  "empty-state": { specimen: "components/controls/empty-states-reference.tsx", route: "/controls", marker: "EmptyState" },
  field: { specimen: "components/controls/select-reference.tsx", route: "/controls", marker: "Field" },
  form: { specimen: "components/controls/form-fields-reference.tsx", route: "/controls", marker: "FormField" },
  "icon-button": { specimen: "components/controls/nav-buttons-reference.tsx", route: "/controls", marker: "IconButton" },
  input: { specimen: "components/controls/form-fields-reference.tsx", route: "/controls", marker: "Input" },
  kbd: { specimen: "components/chrome/kbd-reference.tsx", route: "/chrome", marker: "Kbd" },
  label: { specimen: "components/controls/form-fields-reference.tsx", route: "/controls", marker: "Label" },
  pagination: { specimen: "components/chrome/pagination-reference.tsx", route: "/chrome", marker: "Pagination" },
  pager: { specimen: "components/controls/nav-buttons-reference.tsx", route: "/controls", marker: "Pager" },
  "radio-group": { specimen: "components/controls/form-fields-reference.tsx", route: "/controls", marker: "Radio" },
  "search-bar": { specimen: "components/controls/search-bar-reference.tsx", route: "/controls", marker: "SearchBar" },
  "segmented-control": { specimen: "components/controls/nav-buttons-reference.tsx", route: "/controls", marker: "SegmentedControl" },
  select: { specimen: "components/controls/select-reference.tsx", route: "/controls", marker: "Select" },
  separator: { specimen: "components/controls/kit-surface-reference.tsx", route: "/controls", marker: "Separator" },
  sheet: { specimen: "components/controls/kit-surface-reference.tsx", route: "/controls", marker: "Sheet" },
  skeleton: { specimen: "components/controls/skeleton-reference.tsx", route: "/controls", marker: "Skeleton" },
  slider: { specimen: "components/controls/slider-reference.tsx", route: "/controls", marker: "Slider" },
  switch: { specimen: "components/controls/form-fields-reference.tsx", route: "/controls", marker: "Switch" },
  table: { specimen: "components/controls/kit-surface-reference.tsx", route: "/controls", marker: "TableRowHeader" },
  tabs: { specimen: "components/controls/kit-surface-reference.tsx", route: "/controls", marker: "Tabs" },
  "tags-input": { specimen: "components/controls/tags-input-reference.tsx", route: "/controls", marker: "TagsInput" },
  textarea: { specimen: "components/controls/form-fields-reference.tsx", route: "/controls", marker: "Textarea" },
  tooltip: { specimen: "components/controls/tooltip-reference.tsx", route: "/controls", marker: "Tooltip" },
} as const;
