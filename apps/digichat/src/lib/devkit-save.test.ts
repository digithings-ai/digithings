import { mkdtempSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { describe, expect, it } from "vitest";
import { DEVKIT_SENTINEL, redactSecretLines } from "./devkit-configs";
import {
  makeDevkitTempDir,
  parseDevkitNewFileId,
  parseDevkitSaveId,
  resolveDevkitFilePath,
  restoreDevkitSentinels,
  saveDevkitEntry,
  toConfigDirRel,
  toPickerRel,
} from "./devkit-save";

const FIXTURE = [
  "version: 1",
  "deployment:",
  "  slug: acme",
  "  backend:",
  "    type: digigraph",
  "  token: s3cret-disk-value",
  "  gate:",
  "    mode: ungated",
  "    activityDetail: labels",
  "    consumeUrl: https://quota.example.com/consume",
  "",
].join("\n");

const HOSTS_FIXTURE = [
  "version: 1",
  "deployment:",
  "  slug: main",
  "  backend:",
  "    type: digigraph",
  "hosts:",
  "  one:",
  "    slug: one",
  "    backend:",
  "      type: digigraph",
  "  two:",
  "    slug: two",
  "    backend:",
  "      type: digigraph",
  "",
].join("\n");

function setupFile(dir: string, rel: string, text: string): void {
  writeFileSync(join(dir, rel), text);
}

describe("parseDevkitSaveId", () => {
  it("splits file, hosts-scoped, and env ids", () => {
    expect(parseDevkitSaveId("file:a.yaml")).toEqual({ rel: "a.yaml", scope: ["deployment"] });
    expect(parseDevkitSaveId("file:d/a.yaml#hosts/k")).toEqual({
      rel: "d/a.yaml",
      scope: ["hosts", "k"],
    });
    expect(parseDevkitSaveId("env:example.com")).toBeNull();
    expect(parseDevkitSaveId("bogus")).toBeNull();
  });
});

describe("resolveDevkitFilePath", () => {
  it("contains escapes and non-yaml names", () => {
    const dir = mkdtempSync(`${tmpdir()}/devkit-path-`);
    setupFile(dir, "ok.yaml", "version: 1\n");
    // realpath: tmpdir may be a symlink (macOS /var → /private/var).
    expect(resolveDevkitFilePath(dir, "ok.yaml")).toBe(
      join(realpathSync(dir), "ok.yaml"),
    );
    expect(resolveDevkitFilePath(dir, "../outside.yaml")).toBeNull();
    expect(resolveDevkitFilePath(dir, "/abs.yaml")).toBeNull();
    expect(resolveDevkitFilePath(dir, "nope.json")).toBeNull();
    expect(resolveDevkitFilePath(dir, "missing.yaml")).toBeNull();
  });
});

describe("restoreDevkitSentinels", () => {
  it("restores an untouched redacted round-trip byte-identically", () => {
    const redacted = redactSecretLines(FIXTURE);
    expect(redacted).toContain(DEVKIT_SENTINEL);
    const out = restoreDevkitSentinels(redacted, FIXTURE);
    expect(out).toEqual({ ok: true, text: FIXTURE });
  });

  it("refuses a user-typed sentinel with no disk counterpart", () => {
    // Disk holds no secret lines, so nothing was ever masked.
    const disk = "version: 1\ndeployment:\n  slug: x\n  backend:\n    type: digigraph\n";
    const out = restoreDevkitSentinels(`${disk}  token: __DEVKIT_PRESERVED__\n`, disk);
    expect(out.ok).toBe(false);
  });
});

describe("saveDevkitEntry", () => {
  it("round-trips an untouched draft and writes a .bak", () => {
    const dir = makeDevkitTempDir("devkit-save-");
    setupFile(dir, "acme.yaml", FIXTURE);
    const res = saveDevkitEntry(dir, {
      id: "file:acme.yaml",
      text: redactSecretLines(FIXTURE),
    });
    expect(res).toEqual({ ok: true, id: "file:acme.yaml", backup: "acme.yaml.bak" });
    expect(readFileSync(join(dir, "acme.yaml"), "utf8")).toBe(FIXTURE);
    expect(readFileSync(join(dir, "acme.yaml.bak"), "utf8")).toBe(FIXTURE);
  });

  it("persists non-secret edits while preserving disk secrets", () => {
    const dir = makeDevkitTempDir("devkit-save-");
    setupFile(dir, "acme.yaml", FIXTURE);
    const edited = redactSecretLines(FIXTURE).replace("slug: acme", "slug: acme-v2");
    const res = saveDevkitEntry(dir, { id: "file:acme.yaml", text: edited });
    expect(res.ok).toBe(true);
    const written = readFileSync(join(dir, "acme.yaml"), "utf8");
    expect(written).toContain("slug: acme-v2");
    expect(written).toContain("token: s3cret-disk-value");
    expect(written).not.toContain(DEVKIT_SENTINEL);
  });

  it("writes an explicitly replaced secret value", () => {
    const dir = makeDevkitTempDir("devkit-save-");
    setupFile(dir, "acme.yaml", FIXTURE);
    const edited = redactSecretLines(FIXTURE).replace(
      `token: ${DEVKIT_SENTINEL}`,
      "token: brand-new-value",
    );
    const res = saveDevkitEntry(dir, { id: "file:acme.yaml", text: edited });
    expect(res.ok).toBe(true);
    expect(readFileSync(join(dir, "acme.yaml"), "utf8")).toContain("token: brand-new-value");
  });

  it("refuses invalid YAML without touching disk", () => {
    const dir = makeDevkitTempDir("devkit-save-");
    setupFile(dir, "acme.yaml", FIXTURE);
    const res = saveDevkitEntry(dir, { id: "file:acme.yaml", text: "deployment: [unclosed\n" });
    expect(res.ok).toBe(false);
    expect(readFileSync(join(dir, "acme.yaml"), "utf8")).toBe(FIXTURE);
  });

  it("refuses schema violations without touching disk", () => {
    const dir = makeDevkitTempDir("devkit-save-");
    setupFile(dir, "acme.yaml", FIXTURE);
    const bad = redactSecretLines(FIXTURE).replace("slug: acme", "slug: BAD SLUG");
    const res = saveDevkitEntry(dir, { id: "file:acme.yaml", text: bad });
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.issues.join("\n")).toContain("slug");
    expect(readFileSync(join(dir, "acme.yaml"), "utf8")).toBe(FIXTURE);
  });

  it("refuses env entries, escapes, and missing files", () => {
    const dir = makeDevkitTempDir("devkit-save-");
    setupFile(dir, "acme.yaml", FIXTURE);
    expect(saveDevkitEntry(dir, { id: "env:example.com", text: "x" }).ok).toBe(false);
    expect(saveDevkitEntry(dir, { id: "file:../evil.yaml", text: "x" }).ok).toBe(false);
    expect(saveDevkitEntry(dir, { id: "file:ghost.yaml", text: "x" }).ok).toBe(false);
    expect(readFileSync(join(dir, "acme.yaml"), "utf8")).toBe(FIXTURE);
  });

  it("refuses a tampered redacted line", () => {
    const dir = makeDevkitTempDir("devkit-save-");
    setupFile(dir, "acme.yaml", FIXTURE);
    const tampered = redactSecretLines(FIXTURE).replace(
      `  token: ${DEVKIT_SENTINEL}`,
      `   token: ${DEVKIT_SENTINEL}`,
    );
    const res = saveDevkitEntry(dir, { id: "file:acme.yaml", text: tampered });
    expect(res.ok).toBe(false);
    expect(readFileSync(join(dir, "acme.yaml"), "utf8")).toBe(FIXTURE);
  });

  it("saves a hosts-scoped entry into the parent file only", () => {
    const dir = makeDevkitTempDir("devkit-save-");
    setupFile(dir, "multi.yaml", HOSTS_FIXTURE);
    const edited = HOSTS_FIXTURE.replace("slug: two", "slug: two-v2");
    const res = saveDevkitEntry(dir, { id: "file:multi.yaml#hosts/two", text: edited });
    expect(res.ok).toBe(true);
    const written = readFileSync(join(dir, "multi.yaml"), "utf8");
    expect(written).toContain("slug: two-v2");
    expect(written).toContain("slug: one");
    expect(written).toContain("slug: main");
  });

  it("refuses when the hosts scope vanishes after edit", () => {
    const dir = makeDevkitTempDir("devkit-save-");
    setupFile(dir, "multi.yaml", HOSTS_FIXTURE);
    const dropped = HOSTS_FIXTURE.replace(/  two:\n(?:    .*\n)+/, "");
    const res = saveDevkitEntry(dir, { id: "file:multi.yaml#hosts/two", text: dropped });
    expect(res.ok).toBe(false);
    expect(readFileSync(join(dir, "multi.yaml"), "utf8")).toBe(HOSTS_FIXTURE);
  });
});

const NEW_FILE_TEXT = [
  "version: 1",
  "deployment:",
  "  slug: shiny",
  "  backend:",
  "    type: digigraph",
  "",
].join("\n");

describe("picker/config-dir rel mapping", () => {
  it("strips one leading config-dir basename segment", () => {
    expect(toConfigDirRel("/app/config", "config/a.yaml")).toBe("a.yaml");
    expect(toConfigDirRel("/app/config", "config/examples/a.yaml")).toBe("examples/a.yaml");
    // Double prefix (a literal `config/` dir inside the config dir) keeps one.
    expect(toConfigDirRel("/app/config", "config/config/a.yaml")).toBe("config/a.yaml");
    // Bare names (tmp-dir callers) pass through untouched.
    expect(toConfigDirRel("/tmp/xyz", "a.yaml")).toBe("a.yaml");
    expect(toPickerRel("/app/config", "a.yaml")).toBe("config/a.yaml");
  });

  it("saves a picker-style prefixed id into a production-layout dir", () => {
    // Mirror production: appRoot/config/acme.yaml, ids prefixed `config/`.
    const appRoot = mkdtempSync(`${tmpdir()}/devkit-approot-`);
    const configDir = join(appRoot, "config");
    mkdirSync(configDir);
    setupFile(configDir, "acme.yaml", FIXTURE);
    const res = saveDevkitEntry(configDir, {
      id: "file:config/acme.yaml",
      text: redactSecretLines(FIXTURE),
    });
    expect(res.ok).toBe(true);
    expect(readFileSync(join(configDir, "acme.yaml"), "utf8")).toBe(FIXTURE);
    expect(readFileSync(join(configDir, "acme.yaml.bak"), "utf8")).toBe(FIXTURE);
  });
});

describe("parseDevkitNewFileId", () => {
  it("accepts new:<slug>.yaml and rejects everything else", () => {
    expect(parseDevkitNewFileId("new:shiny.yaml")).toEqual({ rel: "shiny.yaml", slug: "shiny" });
    expect(parseDevkitNewFileId("file:shiny.yaml")).toBeNull();
    expect(parseDevkitNewFileId("new:../evil.yaml")).toBeNull();
    expect(parseDevkitNewFileId("new:SHINY.yaml")).toBeNull();
    expect(parseDevkitNewFileId("new:shiny.json")).toBeNull();
    expect(parseDevkitNewFileId("env:example.com")).toBeNull();
  });
});

describe("saveDevkitEntry new-file creation", () => {
  it("writes config/<slug>.yaml with no .bak and returns the picker id", () => {
    const dir = makeDevkitTempDir("devkit-save-new-");
    const res = saveDevkitEntry(dir, { id: "new:shiny.yaml", text: NEW_FILE_TEXT });
    expect(res).toEqual({ ok: true, id: `file:${basename(dir)}/shiny.yaml`, backup: null });
    expect(readFileSync(join(dir, "shiny.yaml"), "utf8")).toBe(NEW_FILE_TEXT);
  });

  it("refuses when the file already exists (slug uniqueness)", () => {
    const dir = makeDevkitTempDir("devkit-save-new-");
    setupFile(dir, "shiny.yaml", NEW_FILE_TEXT);
    const res = saveDevkitEntry(dir, { id: "new:shiny.yaml", text: NEW_FILE_TEXT });
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.issues.join("\n")).toContain("already exists");
    expect(readFileSync(join(dir, "shiny.yaml"), "utf8")).toBe(NEW_FILE_TEXT);
  });

  it("refuses when the filename slug differs from deployment.slug", () => {
    const dir = makeDevkitTempDir("devkit-save-new-");
    const mismatched = NEW_FILE_TEXT.replace("slug: shiny", "slug: other");
    const res = saveDevkitEntry(dir, { id: "new:third.yaml", text: mismatched });
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.issues.join("\n")).toContain("(slug)");
    expect(() => readFileSync(join(dir, "third.yaml"), "utf8")).toThrow();
  });

  it("refuses sentinels in new files (nothing to restore from)", () => {
    const dir = makeDevkitTempDir("devkit-save-new-");
    const text = `${NEW_FILE_TEXT}  token: ${DEVKIT_SENTINEL}\n`;
    const res = saveDevkitEntry(dir, { id: "new:shiny.yaml", text });
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.issues.join("\n")).toContain("(secrets)");
  });

  it("refuses invalid schema in new files without writing", () => {
    const dir = makeDevkitTempDir("devkit-save-new-");
    const res = saveDevkitEntry(dir, {
      id: "new:shiny.yaml",
      text: "version: 1\ndeployment:\n  slug: shiny\n",
    });
    expect(res.ok).toBe(false);
    expect(() => readFileSync(join(dir, "shiny.yaml"), "utf8")).toThrow();
  });
});
