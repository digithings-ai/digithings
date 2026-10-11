import { mono } from "@/app/fonts";

/**
 * The first-party digichat skin reads `--font-geist-mono`
 * (`packages/ui/src/styles/chat-aui.css`), where that retired name is aliased to
 * this app's `--font-mono-face` — the face `app/fonts.ts` loads. Re-exported
 * under the old name so the chat frame cannot drift onto a second loader: the
 * page ships one Geist Mono woff2, and swapping the face stays a one-line edit
 * in `app/fonts.ts`.
 */
export const digichatFont = mono;

/**
 * Chat text size on digiquant-web: the band and the desk both set it on the
 * chat root, and the thread inherits it. Matches the page body scale (mono reads
 * wider than the sans prose, so it sits a step below the 0.9375rem takeaway).
 */
export const DIGICHAT_TEXT = "text-[0.8125rem] leading-[1.55]";
