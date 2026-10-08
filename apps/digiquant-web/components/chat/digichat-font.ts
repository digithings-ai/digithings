import { mono } from "@/app/fonts";

/**
 * The first-party digichat skin reads `--font-geist-mono`
 * (`packages/ui/src/styles/chat-aui.css`), which `app/fonts.ts` aliases to this
 * app's single mono face. Re-exported under the old name so the chat frame
 * cannot drift onto a second loader: the page ships one Geist Mono woff2, and
 * swapping the face stays a one-line edit in `app/fonts.ts`.
 */
export const digichatFont = mono;