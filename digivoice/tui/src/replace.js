import { FFIType, dlopen, ptr } from "bun:ffi"
import { spawn } from "node:child_process"

function pointerList(values) {
  const strings = values.map((value) => Buffer.from(`${value}\0`))
  const list = new BigUint64Array(values.length + 1)
  strings.forEach((item, index) => {
    list[index] = BigInt(ptr(item))
  })
  list[values.length] = 0n
  return { list, strings }
}

function pythonArgs() {
  const python = process.env.DIGIVOICE_PYTHON || "python"
  try {
    const saved = JSON.parse(process.env.DIGIVOICE_ARGV || "[]")
    if (Array.isArray(saved) && saved.length) return [python, ...saved]
  } catch {
    /* a missing argv falls through to the module */
  }
  return [python, "-m", "digivoice"]
}

/** Replace this process with the Python CLI so the terminal pid stays put. */
export function replaceWithPython() {
  const args = pythonArgs()
  try {
    const libc = dlopen("libc.so.6", {
      execve: {
        args: [FFIType.ptr, FFIType.ptr, FFIType.ptr],
        returns: FFIType.i32,
      },
    })
    const file = Buffer.from(`${args[0]}\0`)
    const argv = pointerList(args)
    const env = pointerList(
      Object.entries(process.env).map(([key, value]) => `${key}=${value ?? ""}`),
    )
    libc.symbols.execve(ptr(file), ptr(argv.list), ptr(env.list))
  } catch {
    const child = spawn(args[0], args.slice(1), { stdio: "inherit" })
    child.on("exit", (code) => process.exit(code ?? 1))
    return
  }
  process.exit(1)
}
