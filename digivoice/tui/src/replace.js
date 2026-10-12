import { FFIType, dlopen, ptr } from "bun:ffi"
import { spawn } from "node:child_process"
import { platform } from "node:os"

function pointerList(values) {
  const strings = values.map((value) => Buffer.from(`${value}\0`))
  const list = new BigUint64Array(values.length + 1)
  strings.forEach((item, index) => {
    list[index] = BigInt(ptr(item))
  })
  list[values.length] = 0n
  return { list, strings }
}

export function libcName(os = platform()) {
  if (os === "darwin") return "/usr/lib/libSystem.B.dylib"
  return "libc.so.6"
}

export function pythonArgs(env = process.env) {
  const python = env.DIGIVOICE_PYTHON || "python"
  try {
    const saved = JSON.parse(env.DIGIVOICE_ARGV || "[]")
    if (Array.isArray(saved) && saved.length) return [python, ...saved]
  } catch {
    /* a missing argv falls through to the module */
  }
  return [python, "-m", "digivoice"]
}

function tryExec(args) {
  const libc = dlopen(libcName(), {
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
}

/** Replace this process with the Python CLI so the terminal pid stays put. */
export function replaceWithPython() {
  const args = pythonArgs()
  try {
    tryExec(args)
  } catch {
    /* dlopen or execve could not replace this process */
  }
  try {
    const child = spawn(args[0], args.slice(1), { stdio: "inherit" })
    child.on("exit", (code) => process.exit(code ?? 1))
    child.on("error", () => process.exit(1))
  } catch {
    process.exit(1)
  }
}
