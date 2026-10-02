import { spawnSync } from "node:child_process"

/** One JSON call into the Python CLI. No network. */
export function pythonSession(env = process.env) {
  const python = env.DIGIVOICE_PYTHON || "python"
  return {
    call(request) {
      const result = spawnSync(python, ["-m", "digivoice.tui_bridge"], {
        input: JSON.stringify(request),
        encoding: "utf8",
        env,
      })
      if (result.status !== 0) {
        const detail = (result.stderr || result.stdout || "bridge failed").trim()
        throw new Error(detail)
      }
      return JSON.parse(result.stdout)
    },
  }
}
