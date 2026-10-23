/**
 * The base path the digichat app is built and served under inside the Container.
 *
 * Next bakes `basePath` at BUILD time (apps/digichat/next.config.ts reads
 * DIGICHAT_BASE_PATH), so this is the same value the image is built with
 * (infra/docker/Dockerfile.digichat-cloudflare). The contract test pins the two
 * together so the edge and the image cannot drift apart.
 *
 * /chat, not /digichat: the app's surface is the ROOT route
 * (apps/digichat/src/app/(digichat)/page.tsx) and there is no src/app/chat
 * directory, so a /chat base path does not nest into /chat/chat.
 *
 * It lives in its own module because `occ-gate.ts` needs it and `paths.ts`
 * already imports the gate: this keeps that dependency one-way.
 */
export const CONTAINER_BASE_PATH = "/chat";
