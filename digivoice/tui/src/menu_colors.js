// Menu paint for a theme payload. Empty palette (no active theme) returns
// null row/status so the terminal keeps its existing white, gray, and
// green/red chrome. A named palette uses text (ink) and accent (primary)
// from that same payload. No palette hex lives here.

export function hexChannels(hex) {
  if (!hex || typeof hex !== "string") return null
  let body = hex.replace("#", "")
  if (body.length === 3) body = body.split("").map((ch) => ch + ch).join("")
  if (body.length !== 6) return null
  const value = Number.parseInt(body, 16)
  if (Number.isNaN(value)) return null
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255]
}

export function menuPaint(theme, truecolor) {
  const active = Boolean(theme && theme.active)
  const text = active ? hexChannels(theme.text) : null
  const accent = active ? hexChannels(theme.accent) : null
  const legacyValue = truecolor ? [175, 175, 175] : { cube: 145 }
  return {
    row: text,
    value: text || legacyValue,
    status: accent,
    statusText: text,
  }
}
