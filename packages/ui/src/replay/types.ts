/**
 * Self-contained digichat replay. The document is the whole conversation the
 * HTML file needs: branding captured from the deployment, the theme the reader
 * was on, and the turns (question, work chain, answer).
 */

export type ReplayThemeMode = "light" | "dark";

export type ReplayView = "quiet" | "balanced" | "verbose";

export type ReplayTheme = {
  /** Stored preference. `auto` follows the OS; the file paints `resolved`. */
  preference: "light" | "dark" | "auto";
  resolved: ReplayThemeMode;
  /** `default` or a palette id from the platform registry. */
  palette: string;
  /** Disclosure density of the live thread (`/view`). */
  view: ReplayView;
};

export type ReplayAccent = {
  color: string;
  foreground: string;
};

export type ReplayNotice = {
  tone: "error" | "status";
  title: string;
  detail: string;
};

export type ReplayToolStatus = "complete" | "error" | "cancelled" | "running";

export type ReplayTool = {
  name: string;
  argsText: string;
  resultText: string;
  status: ReplayToolStatus;
  errorText: string;
};

export type ReplayChainItem =
  | { kind: "reasoning"; text: string }
  | { kind: "tool"; tool: ReplayTool }
  | { kind: "notice"; notice: ReplayNotice };

export type ReplayBlock =
  | { kind: "chain"; items: ReplayChainItem[] }
  | { kind: "text"; markdown: string };

export type ReplayTurn = {
  id: string;
  userText: string;
  blocks: ReplayBlock[];
};

export type ReplayDocument = {
  /** Filename slug. The deployment id, not a display title. */
  deployment: string;
  title: string;
  welcome: string;
  welcomeBody: string[];
  suggestions: string[];
  placeholder: string;
  accent: ReplayAccent | null;
  theme: ReplayTheme;
  /** ISO-8601. The date in the filename is the UTC calendar day of this instant. */
  exportedAt: string;
  turns: ReplayTurn[];
};
