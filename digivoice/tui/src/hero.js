/** Five-row half-block DIGIVOICE wordmark. Cube grays, one color mode. */

const GLYPHS = {
  D: ["######.", "#######", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "#######", "######."],
  I: ["#######", "#######", "..##...", "..##...", "..##...", "..##...", "..##...", "..##...", "#######", "#######"],
  G: [".#####.", "#######", "##.....", "##.....", "##..###", "##..###", "##...##", "##...##", "#######", ".#####."],
  T: ["#######", "#######", "...##..", "...##..", "...##..", "...##..", "...##..", "...##..", "...##..", "...##.."],
  H: ["##...##", "##...##", "##...##", "##...##", "#######", "#######", "##...##", "##...##", "##...##", "##...##"],
  N: ["##...##", "###..##", "###..##", "##.#.##", "##.#.##", "##..###", "##..###", "##...##", "##...##", "##...##"],
  S: [".######", "#######", "##.....", "##.....", "######.", "######.", ".....##", ".....##", "#######", "######."],
  V: ["##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", ".#####.", "..###.."],
  O: [".#####.", "#######", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "#######", ".#####."],
  C: [".#####.", "#######", "##.....", "##.....", "##.....", "##.....", "##.....", "##.....", "#######", ".#####."],
  E: ["#######", "#######", "##.....", "##.....", "######.", "######.", "##.....", "##.....", "#######", "#######"],
}

export const BUILD_MS = 1400
export const HERO_GAP = 2
export const SHADES = [
  { step: 0.36, rgb: 95, cube: 59 },
  { step: 0.5, rgb: 135, cube: 102 },
  { step: 0.66, rgb: 175, cube: 145 },
  { step: 0.82, rgb: 215, cube: 188 },
  { step: 1, rgb: 255, cube: 231 },
]

export function letterGap(cols, letters) {
  for (const gap of [2, 1, 0]) {
    const width = letters * 7 + Math.max(0, letters - 1) * gap
    if (width <= Math.max(1, cols - 2)) return gap
  }
  return 0
}

function gridFor(word, gap) {
  const rows = Array.from({ length: 10 }, () => [])
  const letters = word.toUpperCase()
  for (let index = 0; index < letters.length; index += 1) {
    if (index) {
      for (const row of rows) row.push(...Array(gap).fill(false))
    }
    const glyph = GLYPHS[letters[index]]
    for (let y = 0; y < 10; y += 1) {
      const line = glyph ? glyph[y] : "......."
      for (const mark of line) rows[y].push(mark === "#")
    }
  }
  return rows
}

function filled(grid) {
  const cells = []
  grid.forEach((row, y) => {
    row.forEach((on, x) => {
      if (on) cells.push([x, y])
    })
  })
  return cells
}

function litSet(cells, frac) {
  if (frac >= 1) return new Set(cells.map(([x, y]) => `${x},${y}`))
  const ordered = [...cells].sort((a, b) => ((a[0] * 13 + a[1] * 7) % 97) - ((b[0] * 13 + b[1] * 7) % 97))
  let count = Math.floor(ordered.length * frac)
  if (frac > 0 && count === 0 && ordered.length) count = 1
  return new Set(ordered.slice(0, count).map(([x, y]) => `${x},${y}`))
}

function shadeFor(x, y, tMs) {
  const glint = tMs >= BUILD_MS && (x * 13 + y * 7 + Math.floor(tMs / 180)) % 17 === 0
  if (glint) return SHADES[SHADES.length - 1]
  return SHADES[(x + y) % SHADES.length]
}

/**
 * Five half-block rows. `truecolor` picks RGB; otherwise the cube index.
 * A cell never carries both.
 */
export function wordmarkLines(word = "DIGIVOICE", { cols = 100, tMs = BUILD_MS, truecolor = false } = {}) {
  const letters = word.toUpperCase()
  const gap = letterGap(cols, Math.max(1, letters.length))
  const grid = gridFor(letters, gap)
  const frac = tMs >= BUILD_MS ? 1 : Math.max(0, tMs) / BUILD_MS
  const lit = litSet(filled(grid), frac)
  const lines = []
  for (let y = 0; y < 10; y += 2) {
    const cells = []
    for (let x = 0; x < grid[0].length; x += 1) {
      const top = lit.has(`${x},${y}`)
      const bot = lit.has(`${x},${y + 1}`)
      if (!top && !bot) {
        cells.push({ ch: " ", color: null })
        continue
      }
      let ch = "▄"
      let sy = y + 1
      if (top && bot) {
        ch = "█"
        sy = y
      } else if (top) {
        ch = "▀"
        sy = y
      }
      const shade = shadeFor(x, sy, tMs)
      const color = truecolor ? { rgb: shade.rgb } : { cube: shade.cube }
      cells.push({ ch, color })
    }
    lines.push(cells)
  }
  return { lines, gap, rows: lines.length }
}

export function wordmarkText(word, options) {
  return wordmarkLines(word, options).lines.map((cells) => cells.map((cell) => cell.ch).join(""))
}
