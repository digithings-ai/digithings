/** Browser pages the OpenTUI spine cannot draw. They are not terminal cells. */
export const WEB_SLOTS = [
  { path: "/tools/terminal", label: "Terminal", title: "Terminal" },
  { path: "/tools/luxalgo", label: "LuxAlgo", title: "LuxAlgo" },
  { path: "/tools/charts", label: "Charts", title: "LuxAlgo charts" },
  { path: "/tools/chat", label: "digichat", title: "digichat" },
] as const;

export type WebSlot = (typeof WEB_SLOTS)[number];
