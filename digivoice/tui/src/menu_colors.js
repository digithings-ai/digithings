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

function linearChannel(channel) {
  const c = channel / 255
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

function luminance(channels) {
  return (
    0.2126 * linearChannel(channels[0]) +
    0.7152 * linearChannel(channels[1]) +
    0.0722 * linearChannel(channels[2])
  )
}

function contrast(channels, ground) {
  const high = Math.max(luminance(channels), luminance(ground))
  const low = Math.min(luminance(channels), luminance(ground))
  return (high + 0.05) / (low + 0.05)
}

// Screen paint for the same payload. Empty palette keeps the terminal's
// own background and the old gray wordmark. A named palette paints its
// own neutral as the screen ground; the wordmark ink is the accent when
// it contrasts against that ground, otherwise the palette's own ink.
// No palette hex lives here.
export function screenPaint(theme) {
  const active = Boolean(theme && theme.active)
  if (!active) return { background: null, ink: null, foreground: null }
  const background = hexChannels(theme.bg)
  const ink = hexChannels(theme.text)
  const accent = hexChannels(theme.accent)
  let foreground = ink
  if (accent && background && contrast(accent, background) >= 3) {
    foreground = accent
  }
  return { background, ink, foreground }
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
