/**
 * What a host must provide so a stock skin renders correctly (WS3).
 *
 * "What a skin needs to render correctly" used to be implicit — /baseline
 * learned each item the hard way, one bug at a time. This descriptor names
 * them so a new host mounts `<Skin />` and cannot get it subtly wrong.
 * WS4 carries this contract into the package alongside the skins.
 *
 * Each item cites the file that implements it. The companion test pins every
 * item against the actual sources, so drift fails loudly.
 */
export interface SkinHostContract {
  /** Per-skin scope marker the theme grammar keys off. */
  scopeMarker: {
    attribute: "data-thread-skin";
    /**
     * Hosts set this per skin on their wrapper; the package
     * ThreadPrimitive.Root additionally hard-codes "digichat"
     * (gallery-thread/thread.aui.tsx) so the first-party thread
     * always matches its theme grammar.
     */
    setBy: string[];
  };
  /** Tailwind must scan the kit or kit-only utilities are dropped (diamonds). */
  tailwindSources: {
    hostStylesheet: string;
    sourceDirective: string;
  };
  /** Font variables the grammar references (else the declaration is invalid). */
  fontVariables: {
    variable: "--font-geist-mono";
    hostLayout: string;
  };
  /** Theme dataset + classes the first-party palette hangs off. */
  themeRoot: {
    dataset: "theme";
    classes: ["light", "dark"];
    hostClient: string;
  };
  /** Prefs host gating the `/` palette + `@`-mention. */
  prefsHost: {
    module: string;
    hook: "useStockChatPrefs";
    hostClient: string;
  };
  /** Package stylesheets every stock-skin host must load (WS1). */
  stylesheets: string[];
}

export const DIGICHAT_SKIN_HOST_CONTRACT: SkinHostContract = {
  scopeMarker: {
    attribute: "data-thread-skin",
    // Step 1 (single-route plan): ProductStockShell delegates its render core
    // to DigiChatHost, which now renders the marker for all product/embed
    // traffic. chat-shell + embed-client keep their own wrapper markers.
    setBy: [
      "src/components/stock/digichat-host.tsx",
      "src/components/chat-shell.tsx",
      "src/app/(digichat)/embed/embed-client.tsx",
    ],
  },
  tailwindSources: {
    hostStylesheet: "src/app/(baseline)/baseline.css",
    sourceDirective: '@source "../../../../../packages/ui/src/components/chat"',
  },
  fontVariables: {
    variable: "--font-geist-mono",
    hostLayout: "src/app/(baseline)/layout.tsx",
  },
  themeRoot: {
    dataset: "theme",
    classes: ["light", "dark"],
    hostClient: "src/app/(baseline)/baseline/baseline-client.tsx",
  },
  prefsHost: {
    module: "@digithings/ui/chat/stock",
    hook: "useStockChatPrefs",
    hostClient: "src/app/(baseline)/baseline/baseline-client.tsx",
  },
  stylesheets: [
    "@digithings/ui/styles/digichat-app-theme.css",
    "@digithings/ui/styles/chat-digichat.css",
  ],
};
