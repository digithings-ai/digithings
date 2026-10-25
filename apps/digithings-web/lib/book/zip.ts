/**
 * A minimal ZIP writer, stored (uncompressed) entries only.
 *
 * The Word export needs a real OOXML package, and an OOXML package is a ZIP.
 * The alternative was a dependency: the app has none for archives (`pako` is
 * here, but only as pdf-lib's deflate stream, which still leaves the container
 * headers to write), and a DOCX with a handful of XML parts fits in a few
 * hundred bytes of header code. So this is deliberately small: no compression,
 * no data descriptors, no ZIP64 — sizes and offsets are known before a byte is
 * written, which is true for every part we build.
 *
 * Word, LibreOffice and Pages all accept stored entries.
 */

const LOCAL_HEADER = 0x04034b50;
const CENTRAL_HEADER = 0x02014b50;
const END_OF_DIRECTORY = 0x06054b50;

/** UTF-8 names, so an entry name can never be read with the wrong codepage. */
const FLAG_UTF8 = 0x0800;
const METHOD_STORED = 0;

/**
 * 1980-01-01 00:00 — the earliest DOS timestamp. Fixed on purpose: the same
 * book exported twice should be the same bytes, so a test can compare them.
 */
const DOS_TIME = 0;
const DOS_DATE = 0x0021;

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let index = 0; index < 256; index += 1) {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) {
      value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    }
    table[index] = value >>> 0;
  }
  return table;
})();

/** Standard CRC-32 (the one ZIP entries are keyed by). */
export function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (let index = 0; index < bytes.length; index += 1) {
    crc = (CRC_TABLE[(crc ^ bytes[index]) & 0xff] as number) ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

export type ZipEntry = { name: string; data: Uint8Array };

function utf8(text: string): Uint8Array {
  return new TextEncoder().encode(text);
}

/** The whole archive: local entries, then the central directory, then EOCD. */
export function storedZip(entries: readonly ZipEntry[]): Uint8Array {
  const prepared = entries.map((entry) => ({
    name: utf8(entry.name),
    data: entry.data,
    crc: crc32(entry.data),
  }));

  const localSize = prepared.reduce(
    (total, entry) => total + 30 + entry.name.length + entry.data.length,
    0,
  );
  const centralSize = prepared.reduce(
    (total, entry) => total + 46 + entry.name.length,
    0,
  );
  const out = new Uint8Array(localSize + centralSize + 22);
  const view = new DataView(out.buffer);
  let offset = 0;

  const offsets: number[] = [];
  for (const entry of prepared) {
    offsets.push(offset);
    view.setUint32(offset, LOCAL_HEADER, true);
    view.setUint16(offset + 4, 20, true);
    view.setUint16(offset + 6, FLAG_UTF8, true);
    view.setUint16(offset + 8, METHOD_STORED, true);
    view.setUint16(offset + 10, DOS_TIME, true);
    view.setUint16(offset + 12, DOS_DATE, true);
    view.setUint32(offset + 14, entry.crc, true);
    view.setUint32(offset + 18, entry.data.length, true);
    view.setUint32(offset + 22, entry.data.length, true);
    view.setUint16(offset + 26, entry.name.length, true);
    view.setUint16(offset + 28, 0, true);
    out.set(entry.name, offset + 30);
    out.set(entry.data, offset + 30 + entry.name.length);
    offset += 30 + entry.name.length + entry.data.length;
  }

  const directoryStart = offset;
  prepared.forEach((entry, index) => {
    view.setUint32(offset, CENTRAL_HEADER, true);
    view.setUint16(offset + 4, 20, true);
    view.setUint16(offset + 6, 20, true);
    view.setUint16(offset + 8, FLAG_UTF8, true);
    view.setUint16(offset + 10, METHOD_STORED, true);
    view.setUint16(offset + 12, DOS_TIME, true);
    view.setUint16(offset + 14, DOS_DATE, true);
    view.setUint32(offset + 16, entry.crc, true);
    view.setUint32(offset + 20, entry.data.length, true);
    view.setUint32(offset + 24, entry.data.length, true);
    view.setUint16(offset + 28, entry.name.length, true);
    view.setUint16(offset + 30, 0, true);
    view.setUint16(offset + 32, 0, true);
    view.setUint16(offset + 34, 0, true);
    view.setUint16(offset + 36, 0, true);
    view.setUint32(offset + 38, 0, true);
    view.setUint32(offset + 42, offsets[index] ?? 0, true);
    out.set(entry.name, offset + 46);
    offset += 46 + entry.name.length;
  });

  view.setUint32(offset, END_OF_DIRECTORY, true);
  view.setUint16(offset + 4, 0, true);
  view.setUint16(offset + 6, 0, true);
  view.setUint16(offset + 8, prepared.length, true);
  view.setUint16(offset + 10, prepared.length, true);
  view.setUint32(offset + 12, offset - directoryStart, true);
  view.setUint32(offset + 16, directoryStart, true);
  view.setUint16(offset + 20, 0, true);

  return out;
}
