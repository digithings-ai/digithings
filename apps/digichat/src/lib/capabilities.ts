/**
 * Which verticals the BFF treats as active (health probes, optional URLs).
 * Env: DIGICHAT_ENABLED_SERVICES=digigraph,digisearch,digiquant,digismith
 */
export function getEnabledServiceIds(): string[] {
  const envVar = process.env.DIGICHAT_ENABLED_SERVICES;
  const fallback = "digigraph,digisearch,digiquant,digismith";
  const s = envVar === undefined ? fallback : envVar;
  return [...new Set(s.split(",").map((x) => x.trim()).filter(Boolean))];
}

export function isServiceCapabilityEnabled(id: string): boolean {
  return getEnabledServiceIds().includes(id);
}
