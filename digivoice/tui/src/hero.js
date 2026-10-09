/** Half-block DIGIVOICE wordmark. Square pixels, one color mode. */

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
export const GLYPH_COLS = 7
export const GLYPH_ROWS = 10
export const SHADES = [
  { step: 0.36, rgb: 95, cube: 59 },
  { step: 0.5, rgb: 135, cube: 102 },
  { step: 0.66, rgb: 175, cube: 145 },
  { step: 0.82, rgb: 215, cube: 188 },
  { step: 1, rgb: 255, cube: 231 },
]
export const REST_SHADE = SHADES[1]
export const LIT_SHADE = SHADES[SHADES.length - 1]

const CHROME_BESIDE_SLOT = HERO_GAP + 1 + 3 + 1 + HERO_GAP

export function wordWidth(letters, gap, scale = 1) {
  const count = Math.max(1, letters)
  return (count * GLYPH_COLS + Math.max(0, count - 1) * gap) * scale
}

export function letterGap(cols, letters, scale = 1) {
  const budget = Math.max(1, cols - 2)
  for (const gap of [2, 1, 0]) {
    if (wordWidth(letters, gap, scale) <= budget) return gap
  }
  return 0
}

export function faceRowsFor(scale) {
  return (GLYPH_ROWS * scale) / 2
}

export function slotRowsFor(scale) {
  return faceRowsFor(scale) + 1
}

export function pixelScale({ cols = 80, rows, letters = 9 } = {}) {
  const count = Math.max(1, letters)
  const budget = Math.max(1, cols - 2)
  for (const scale of [3, 2, 1]) {
    if (wordWidth(count, 0, scale) > budget && scale > 1) continue
    if (rows != null && Number.isFinite(rows) && rows > 0) {
      const chrome = slotRowsFor(scale) + CHROME_BESIDE_SLOT
      if (rows < chrome && scale > 1) continue
    }
    return scale
  }
  return 1
}

function gridFor(word, gap) {
  const rows = Array.from({ length: GLYPH_ROWS }, () => [])
  const letters = word.toUpperCase()
  for (let index = 0; index < letters.length; index += 1) {
    if (index) {
      for (const row of rows) row.push(...Array(gap).fill(false))
    }
    const glyph = GLYPHS[letters[index]]
    for (let y = 0; y < GLYPH_ROWS; y += 1) {
      const line = glyph ? glyph[y] : "......."
      for (const mark of line) rows[y].push(mark === "#")
    }
  }
  return rows
}

function scaleGrid(grid, scale) {
  if (scale <= 1) return grid
  const rows = []
  for (const row of grid) {
    const wide = []
    for (const on of row) {
      for (let step = 0; step < scale; step += 1) wide.push(on)
    }
    for (let step = 0; step < scale; step += 1) rows.push(wide.slice())
  }
  return rows
}

function levelFrac(column, tMs) {
  const t = Math.max(0, Number.isFinite(tMs) ? tMs : 0)
  const slow = Math.sin(t / 380 + column * 0.73)
  const fast = Math.sin(t / 170 + column * 1.37)
  return (slow * 0.65 + fast * 0.35 + 1) / 2
}

function voiceCubes(grid, tMs, scale) {
  const cubes = []
  const width = grid[0].length
  for (let x = 0; x < width; x += 1) {
    const ys = []
    for (let y = 0; y < grid.length; y += 1) {
      if (grid[y][x]) ys.push(y)
    }
    ys.sort((a, b) => b - a)
    const reach = levelFrac(Math.floor(x / scale), tMs) * ys.length
    ys.forEach((y, index) => {
      cubes.push({ x, y, bright: index < reach })
    })
  }
  return cubes
}

function colorOf(bright, truecolor, ink) {
  if (ink && truecolor) {
    const scale = bright ? 1 : 0.62
    return {
      rgb: [
        Math.round(ink[0] * scale),
        Math.round(ink[1] * scale),
        Math.round(ink[2] * scale),
      ],
    }
  }
  const shade = bright ? LIT_SHADE : REST_SHADE
  return truecolor ? { rgb: shade.rgb } : { cube: shade.cube }
}

/**
 * Half-block rows. Each glyph cell is a square pixel grid: 3×3 when it fits,
 * otherwise 2×2, otherwise 1×1. `truecolor` picks RGB; otherwise the cube index.
 * A cell never carries both. Pixels rest gray and brighten from the bottom of
 * each column while a level rises and falls. Gaps stay empty.
 */
export function wordmarkLines(word = "DIGIVOICE", options = {}) {
  const { cols = 100, rows, tMs = BUILD_MS, truecolor = false, ink = null } = options
  const letters = word.toUpperCase()
  const count = Math.max(1, letters.length)
  const scale = options.scale ?? pixelScale({ cols, rows, letters: count })
  const gap = letterGap(cols, count, scale)
  const grid = scaleGrid(gridFor(letters, gap), scale)
  const cubes = voiceCubes(grid, tMs, scale)
  const brightAt = new Map(cubes.map((cube) => [`${cube.x},${cube.y}`, cube.bright]))
  const lines = []
  for (let y = 0; y < grid.length; y += 2) {
    const cells = []
    for (let x = 0; x < grid[0].length; x += 1) {
      const topOn = grid[y][x]
      const botOn = grid[y + 1][x]
      if (!topOn && !botOn) {
        cells.push({ ch: " ", color: null })
        continue
      }
      if (topOn && botOn) {
        cells.push({
          ch: "▀",
          color: colorOf(brightAt.get(`${x},${y}`) === true, truecolor, ink),
          bg: colorOf(brightAt.get(`${x},${y + 1}`) === true, truecolor, ink),
        })
        continue
      }
      const yOn = topOn ? y : y + 1
      cells.push({
        ch: topOn ? "▀" : "▄",
        color: colorOf(brightAt.get(`${x},${yOn}`) === true, truecolor, ink),
      })
    }
    lines.push(cells)
  }
  return { lines, gap, rows: lines.length, cubes, scale }
}

export function wordmarkText(word, options) {
  return wordmarkLines(word, options).lines.map((cells) => cells.map((cell) => cell.ch).join(""))
}
