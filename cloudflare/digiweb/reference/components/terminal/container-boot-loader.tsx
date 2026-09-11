/**
 * Container-boot loader — the full-surface wait shown while the app's container
 * is still coming up, naming the phase instead of spinning at the reader.
 *
 * PROMOTED to `@digithings/web`; consume it from there. The implementation and
 * the full docblock live in `web/src/components/terminal/ContainerBootLoader.tsx`,
 * and the `.tl-boot*` styles in `@digithings/web/styles/terminal-loaders.css`.
 * This file stays as the re-export so the specimen keeps a stable import path
 * while there is exactly one implementation to drift from.
 */
export {
  ContainerBootLoader,
  CONTAINER_BOOT_STEPS,
  type ContainerBootLoaderProps,
} from "@digithings/web";
