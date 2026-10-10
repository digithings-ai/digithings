import { spawn, spawnSync } from "node:child_process"

/** One JSON call into the Python CLI. A download streams one JSON object per line. */
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
    follow(request, onLine) {
      const child = spawn(python, ["-m", "digivoice.tui_bridge"], {
        env,
        stdio: ["pipe", "pipe", "pipe"],
      })
      let buffer = ""
      child.stdout.setEncoding("utf8")
      child.stdout.on("data", (chunk) => {
        buffer += chunk
        let newline = buffer.indexOf("\n")
        while (newline >= 0) {
          const line = buffer.slice(0, newline).trim()
          buffer = buffer.slice(newline + 1)
          if (line) onLine(JSON.parse(line))
          newline = buffer.indexOf("\n")
        }
      })
      child.stdin.end(JSON.stringify(request))
      return {
        cancel() {
          child.kill()
        },
      }
    },
  }
}
