import { describe, expect, it } from "vitest";

import { crc32, storedZip } from "./zip";

const bytes = (text: string) => new TextEncoder().encode(text);

function asText(data: Uint8Array): string {
  return new TextDecoder("latin1").decode(data);
}

describe("crc32", () => {
  it("matches the reference check value", () => {
    // The CRC-32 check value every implementation is measured against.
    expect(crc32(bytes("123456789"))).toBe(0xcbf43926);
    expect(crc32(new Uint8Array())).toBe(0);
  });
});

describe("storedZip", () => {
  it("writes a readable archive: local header, stored bytes, central directory, EOCD", () => {
    const archive = storedZip([
      { name: "[Content_Types].xml", data: bytes("<Types/>") },
      { name: "word/document.xml", data: bytes("<w:document/>") },
    ]);

    expect(archive[0]).toBe(0x50); // P
    expect(archive[1]).toBe(0x4b); // K
    expect(archive[2]).toBe(0x03);
    expect(archive[3]).toBe(0x04);

    const text = asText(archive);
    expect(text).toContain("[Content_Types].xml");
    expect(text).toContain("word/document.xml");
    // Stored, not deflated: the payload is legible inside the archive.
    expect(text).toContain("<w:document/>");
    // End of central directory, with the entry count.
    expect(text).toContain("PK\u0005\u0006");
    expect(text).toContain("PK\u0001\u0002");
  });

  it("is deterministic, so the same book exports byte for byte the same", () => {
    const build = () => storedZip([{ name: "a.txt", data: bytes("one") }, { name: "b.txt", data: bytes("two") }]);
    expect(asText(build())).toBe(asText(build()));
  });
});
