import assert from "node:assert/strict"
import test from "node:test"

import { libcName, pythonArgs } from "../src/replace.js"

test("restart uses the host libc", () => {
  assert.equal(libcName("darwin"), "/usr/lib/libSystem.B.dylib")
  assert.equal(libcName("linux"), "libc.so.6")
})

test("restart argv is the saved python command", () => {
  assert.deepEqual(
    pythonArgs({
      DIGIVOICE_PYTHON: "/usr/bin/python3",
      DIGIVOICE_ARGV: JSON.stringify(["/usr/local/bin/digivoice"]),
    }),
    ["/usr/bin/python3", "/usr/local/bin/digivoice"],
  )
  assert.deepEqual(pythonArgs({ DIGIVOICE_PYTHON: "/usr/bin/python3", DIGIVOICE_ARGV: "" }), [
    "/usr/bin/python3",
    "-m",
    "digivoice",
  ])
})
