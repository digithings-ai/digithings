import { createCliRenderer } from "@opentui/core"

import { mountDigivoice, onHangup } from "./app.js"
import { replaceWithPython } from "./replace.js"
import { pythonSession } from "./session.js"

async function start() {
  const truecolor = ["truecolor", "24bit"].includes(
    String(process.env.COLORTERM || "").toLowerCase(),
  )
  const session = pythonSession()
  const renderer = await createCliRenderer({
    exitOnCtrlC: true,
    useMouse: true,
  })

  let app
  const hangup = () => {
    onHangup(session)
    if (app) app.destroy()
    renderer.destroy()
    process.exit(0)
  }
  process.on("SIGHUP", hangup)

  try {
    app = mountDigivoice(renderer, session, {
      start: process.env.DIGIVOICE_TUI_START || "/",
      truecolor,
    })
    const code = await app.done
    const restart = app.restarting
    app.destroy()
    renderer.destroy()
    if (restart) {
      replaceWithPython()
      process.exit(0)
    }
    process.exit(code)
  } catch (error) {
    renderer.destroy()
    process.stderr.write(`digivoice: ${error instanceof Error ? error.message : error}\n`)
    process.exit(1)
  }
}

await start()
