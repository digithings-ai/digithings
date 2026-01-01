/**
 * The one hex-colour shape accepted anywhere in digichat: `#rrggbb`.
 *
 * Three modules under `src/lib` used to declare this RegExp literal
 * separately — the embed tenant registry, the embed accent-style helper and
 * the deployment-config schema. They now share this declaration so the
 * accepted shape cannot drift between a tenant entry, an accent override and
 * a deploy config: a colour the tenant registry accepts must also be one the
 * accent helper and the schema accept.
 */
export const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;
