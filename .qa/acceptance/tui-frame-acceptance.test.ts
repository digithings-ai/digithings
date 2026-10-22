/**
 * QA acceptance kit for DIG-5204: the digichat recorded frame lands in the
 * dashboard manifest and renders (DIG-2698, matrix row D9).
 *
 * @vitest-environment happy-dom
 *
 * The issue names three acceptance conditions, with both slices in `develop`:
 *
 *   1. the manifest names the digichat frame with its exporter and route;
 *   2. the dashboard renders that frame;
 *   3. the record shape agrees field for field between producer and consumer.
 *
 * This kit checks all three mechanically against the working tree, reading
 * the producer (`clients/digichat-tui/`) and the consumer
 * (`apps/dashboard/`) side by side. It is a local eval artifact for the QA
 * seat; the shipped version belongs to the dashboard fix PR.
 */

import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import ts from 'typescript';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import TuiRecordedFrames from '@/components/tui-recorded-frames';
import { isRecordedTuiFrame } from '@/lib/tui-preview';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '../..');
const DASHBOARD = join(REPO_ROOT, 'apps/dashboard');
const FIXTURES_DIR = join(DASHBOARD, 'fixtures/tui-frames');
const MANIFEST_PATH = join(FIXTURES_DIR, 'manifest.json');

/** The digichat client, producer side. */
const CLIENT = join(REPO_ROOT, 'clients/digichat-tui');
/** Where the digichat exporter writes its own copy of the record. */
const CLIENT_RECORD = join(CLIENT, 'fixtures/digichat-tui.json');
/** The producer's record type. */
const PRODUCER_TYPE_FILE = join(CLIENT, 'src/frame.ts');
const PRODUCER_TYPE_NAME = 'RecordedFrame';
/** The consumer's record type. */
const CONSUMER_TYPE_FILE = join(DASHBOARD, 'lib/tui-preview.ts');
const CONSUMER_TYPE_NAME = 'RecordedTuiFrame';

const DIGICHAT_SOURCE = 'digichat-tui';
const DIGICHAT_EXPORTER = 'clients/digichat-tui/src/export-frame.ts';

type FrameEntry = { source: string; path: string; file: string; exporter: string };
type Manifest = { version: number; frames: FrameEntry[]; screenshots: unknown[] };

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function loadManifest(): Manifest {
  return JSON.parse(readFileSync(MANIFEST_PATH, 'utf8')) as Manifest;
}

/** The members of a declared object type, read with the TypeScript compiler. */
function typeMembers(file: string, typeName: string): Record<string, string> {
  const program = ts.createProgram([file], {
    target: ts.ScriptTarget.ESNext,
    module: ts.ModuleKind.ESNext,
    strict: true,
    noEmit: true,
  });
  const checker = program.getTypeChecker();
  const source = program.getSourceFile(file);
  if (!source) throw new Error(`cannot read ${file}`);
  let members: Record<string, string> | undefined;
  const visit = (node: ts.Node) => {
    if (ts.isTypeAliasDeclaration(node) && node.name.text === typeName) {
      const type = checker.getTypeFromTypeNode(node.type);
      const found: Record<string, string> = {};
      for (const prop of type.getProperties()) {
        found[prop.name] = checker.typeToString(
          checker.getTypeOfSymbolAtLocation(prop, node),
        );
      }
      members = found;
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  if (!members) throw new Error(`${typeName} is not declared in ${file}`);
  return members;
}

/** The route the digichat exporter records, read from the exporter itself. */
function producerRoute(): string {
  const capture = readFileSync(join(CLIENT, 'src/capture.tsx'), 'utf8');
  const match = capture.match(/export const DEFAULT_PATH\s*=\s*"([^"]+)"/);
  if (!match) throw new Error('the digichat exporter declares no DEFAULT_PATH');
  return match[1];
}

/** The record the producer committed, when it kept a copy of its own. */
function producerRecord(): Record<string, unknown> | undefined {
  if (!existsSync(CLIENT_RECORD)) return undefined;
  return JSON.parse(readFileSync(CLIENT_RECORD, 'utf8')) as Record<string, unknown>;
}

describe('DIG-5204 acceptance: the digichat recorded frame reaches the dashboard', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  describe('1. the manifest names the digichat frame with its exporter and route', () => {
    it('names the digichat frame', () => {
      const manifest = loadManifest();
      const entry = manifest.frames.find((frame) => frame.source === DIGICHAT_SOURCE);
      expect(
        entry,
        `the dashboard manifest names no ${DIGICHAT_SOURCE} frame; it names ${manifest.frames
          .map((frame) => frame.source)
          .join(', ')}`,
      ).toBeDefined();
    });

    it('names the exporter that produces it, and that exporter exists', () => {
      const manifest = loadManifest();
      const entry = manifest.frames.find((frame) => frame.source === DIGICHAT_SOURCE);
      expect(entry).toBeDefined();
      expect(entry!.exporter).toBe(DIGICHAT_EXPORTER);
      expect(
        existsSync(join(REPO_ROOT, entry!.exporter)),
        `${entry!.exporter} does not exist in the tree`,
      ).toBe(true);
    });

    it('names the route the exporter records', () => {
      const manifest = loadManifest();
      const entry = manifest.frames.find((frame) => frame.source === DIGICHAT_SOURCE);
      expect(entry).toBeDefined();
      expect(entry!.path).toBe(producerRoute());
    });

    it('points at a frame file the dashboard actually holds', () => {
      const manifest = loadManifest();
      const entry = manifest.frames.find((frame) => frame.source === DIGICHAT_SOURCE);
      expect(entry).toBeDefined();
      expect(
        existsSync(join(FIXTURES_DIR, entry!.file)),
        `the dashboard holds no copy of the ${DIGICHAT_SOURCE} frame at fixtures/tui-frames/${entry!.file}`,
      ).toBe(true);
    });
  });

  describe('2. the dashboard renders that frame', () => {
    it('renders every frame the manifest names', () => {
      const manifest = loadManifest();
      act(() => {
        root.render(createElement(TuiRecordedFrames, {}));
      });
      const details = container.querySelectorAll('details');
      expect(
        details.length,
        `the manifest names ${manifest.frames.length} frame(s) and the desk pane renders ${details.length}`,
      ).toBe(manifest.frames.length);
    });

    it('renders the digichat frame with its source and route', () => {
      act(() => {
        root.render(createElement(TuiRecordedFrames, {}));
      });
      const summaries = Array.from(container.querySelectorAll('summary')).map(
        (node) => node.textContent ?? '',
      );
      expect(
        summaries.some((text) => text.includes(DIGICHAT_SOURCE)),
        `the desk pane renders no ${DIGICHAT_SOURCE} frame; it renders ${summaries.length} frame(s)`,
      ).toBe(true);
    });

    it('renders the digichat frame text, byte for byte, from the dashboard copy', () => {
      const manifest = loadManifest();
      const entry = manifest.frames.find((frame) => frame.source === DIGICHAT_SOURCE);
      expect(entry).toBeDefined();
      const copy = JSON.parse(
        readFileSync(join(FIXTURES_DIR, entry!.file), 'utf8'),
      ) as { frame: string };
      act(() => {
        root.render(createElement(TuiRecordedFrames, {}));
      });
      const pres = Array.from(container.querySelectorAll('pre.font-mono')).map(
        (node) => node.textContent ?? '',
      );
      expect(pres).toContain(copy.frame);
    });
  });

  describe('3. the record shape agrees field for field between producer and consumer', () => {
    it('declares the same fields, with the same types, on both sides', () => {
      const producer = typeMembers(PRODUCER_TYPE_FILE, PRODUCER_TYPE_NAME);
      const consumer = typeMembers(CONSUMER_TYPE_FILE, CONSUMER_TYPE_NAME);
      expect(
        producer,
        `the producer record type and the consumer record type disagree; consumer declares ${JSON.stringify(consumer)}`,
      ).toEqual(consumer);
    });

    it('writes exactly the consumer fields in the record it produces', () => {
      const consumer = typeMembers(CONSUMER_TYPE_FILE, CONSUMER_TYPE_NAME);
      const record = producerRecord();
      expect(record, 'the digichat exporter committed no record of its own').toBeDefined();
      expect(Object.keys(record!).sort()).toEqual(Object.keys(consumer).sort());
    });

    it('produces a record the consumer accepts', () => {
      const record = producerRecord();
      expect(record).toBeDefined();
      expect(isRecordedTuiFrame(record)).toBe(true);
    });

    it('copies the producer record into the dashboard unchanged', () => {
      const manifest = loadManifest();
      const entry = manifest.frames.find((frame) => frame.source === DIGICHAT_SOURCE);
      expect(entry).toBeDefined();
      const copy = JSON.parse(
        readFileSync(join(FIXTURES_DIR, entry!.file), 'utf8'),
      ) as Record<string, unknown>;
      const record = producerRecord();
      if (!record) return; // the exporter writes straight into the dashboard tree
      expect({ ...copy, capturedAt: null }).toEqual({ ...record, capturedAt: null });
    });
  });
});
