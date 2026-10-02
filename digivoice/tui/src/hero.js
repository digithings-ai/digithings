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
export const REST_SHADE = SHADES[1]
export const LIT_SHADE = SHADES[SHADES.length - 1]

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

function levelFrac(x, tMs) {
  const t = Math.max(0, Number.isFinite(tMs) ? tMs : 0)
  const slow = Math.sin(t / 380 + x * 0.73)
  const fast = Math.sin(t / 170 + x * 1.37)
  return (slow * 0.65 + fast * 0.35 + 1) / 2
}

function voiceCubes(grid, tMs) {
  const cubes = []
  const width = grid[0].length
  for (let x = 0; x < width; x += 1) {
    const ys = []
    for (let y = 0; y < grid.length; y += 1) {
      if (grid[y][x]) ys.push(y)
    }
    ys.sort((a, b) => b - a)
    const reach = levelFrac(x, tMs) * ys.length
    ys.forEach((y, index) => {
      cubes.push({ x, y, bright: index < reach })
    })
  }
  return cubes
}

function colorOf(bright, truecolor) {
  const shade = bright ? LIT_SHADE : REST_SHADE
  return truecolor ? { rgb: shade.rgb } : { cube: shade.cube }
}

/**
 * Five half-block rows. `truecolor` picks RGB; otherwise the cube index.
 * A cell never carries both. Letter cubes rest gray and brighten from the
 * bottom of each column while a level rises and falls. Gaps stay empty.
 */
export function wordmarkLines(word = "DIGIVOICE", { cols = 100, tMs = BUILD_MS, truecolor = false } = {}) {
  const letters = word.toUpperCase()
  const gap = letterGap(cols, Math.max(1, letters.length))
  const grid = gridFor(letters, gap)
  const cubes = voiceCubes(grid, tMs)
  const brightAt = new Map(cubes.map((cube) => [`${cube.x},${cube.y}`, cube.bright]))
  const lines = []
  for (let y = 0; y < 10; y += 2) {
    const cells = []
    for (let x = 0; x < grid[0].length; x += 1) {
      const topOn = grid[y][x]
      const botOn = grid[y + 1][x]
      if (!topOn && !botOn) {
        cells.push({ ch: " ", color: null })
        continue
      }
      let ch = "▄"
      let bright = brightAt.get(`${x},${y + 1}`) === true
      if (topOn && botOn) {
        ch = "█"
        bright = brightAt.get(`${x},${y}`) === true && brightAt.get(`${x},${y + 1}`) === true
      } else if (topOn) {
        ch = "▀"
        bright = brightAt.get(`${x},${y}`) === true
      }
      cells.push({ ch, color: colorOf(bright, truecolor) })
    }
    lines.push(cells)
  }
  return { lines, gap, rows: lines.length, cubes }
}

export function wordmarkText(word, options) {
  return wordmarkLines(word, options).lines.map((cells) => cells.map((cell) => cell.ch).join(""))
}
