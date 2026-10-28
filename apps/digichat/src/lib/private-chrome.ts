/**
 * Private session chrome: the visible copy a private session shows in place of
 * the tenant's own. A private session presents as a generic support desk, so
 * nothing on screen names the tenant, its product or its ticketing system.
 *
 * Outside a private session the tenant's copy is returned unchanged.
 */

export const PRIVATE_WELCOME = "Ask about support.";
export const PRIVATE_PLACEHOLDER = "Ask about support";
export const PRIVATE_HEADER_TITLE = "Support";
export const PRIVATE_SUGGESTIONS: readonly string[] = [
  "How do I file a support ticket?",
  "Show my open support tickets",
  "Where can I find the help documentation?",
  "Summarize this week's support tickets",
];

export type ChromeCopy = {
  welcome: string | undefined;
  placeholder: string;
  suggestions: string[];
  headerTitle: string | undefined;
};

export function privateSessionChrome(privateMode: boolean, tenant: ChromeCopy): ChromeCopy {
  if (!privateMode) return tenant;
  return {
    welcome: PRIVATE_WELCOME,
    placeholder: PRIVATE_PLACEHOLDER,
    suggestions: [...PRIVATE_SUGGESTIONS],
    headerTitle: tenant.headerTitle ? PRIVATE_HEADER_TITLE : tenant.headerTitle,
  };
}
