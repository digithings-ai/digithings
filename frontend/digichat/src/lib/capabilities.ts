/**
 * Which verticals the BFF treats as active (health probes, optional URLs).
 * Env: DIGICHAT_ENABLED_SERVICES=digigraph,digisearch,digiquant,digismith
 */
export function getEnabledServiceIds(): string[] {
  const raw = process.env.DIGICHAT_ENABLED_SERVICES?.trim();
  const fallback = "digigraph,digisearch,digiquant,digismith";
  const s = raw || fallback;
  return [...new Set(s.split(",").map((x) => x.trim()).filter(Boolean))];
}

export function isServiceCapabilityEnabled(id: string): boolean {
  return getEnabledServiceIds().includes(id);
}
