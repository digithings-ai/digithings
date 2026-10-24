/** Browser pages the OpenTUI spine cannot draw. They are not terminal cells. */
export const WEB_SLOTS = [
  { path: "/tools/terminal", label: "Terminal", title: "Terminal" },
  { path: "/tools/gloomberb", label: "Gloomberb", title: "Gloomberb" },
  { path: "/tools/vela", label: "Vela", title: "Vela" },
  { path: "/tools/digichat", label: "digichat", title: "digichat" },
] as const;

export type WebSlot = (typeof WEB_SLOTS)[number];
