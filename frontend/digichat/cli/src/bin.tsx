#!/usr/bin/env node
/**
 * digichat Ink CLI — talks to the same POST /api/chat BFF as the web app.
 * Never imported by the Next.js client bundle.
 *
 * Env:
 *   DIGICHAT_URL          BFF origin (required unless --demo)
 *   DIGICHAT_EMBED_TOKEN  X-Embed-Token (embed installs)
 *   DIGICHAT_EMBED_HOST   X-Embed-Host (optional)
 *   DIGICHAT_API_KEY      Bearer API key (session installs)
 *   DIGICHAT_CONFIG       Path to digichat.yaml — when set, requires cli.enabled: true
 *   DIGICHAT_MODEL        Optional X-Digi-Model
 *   DIGICHAT_LANGUAGE     Optional X-Digi-Language
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { load as loadYaml } from "js-yaml";
import { render } from "ink";
import { DigichatCliApp } from "./app.js";
import {
  assertCliEnabled,
  type DigichatCliAuth,
} from "./chat-request.js";

function readFlag(argv: string[], name: string): string | undefined {
  const idx = argv.indexOf(name);
  if (idx === -1) return undefined;
  return argv[idx + 1];
}

function loadConfigIfRequested(argv: string[]): void {
  const configPath =
    readFlag(argv, "--config") || process.env.DIGICHAT_CONFIG?.trim();
  if (!configPath) return;
  const raw = readFileSync(resolve(configPath), "utf8");
  const doc = loadYaml(raw) as {
    deployment?: { cli?: { enabled?: boolean } };
    cli?: { enabled?: boolean };
  };
  const cliBlock = doc.deployment?.cli ?? doc.cli;
  assertCliEnabled({ cli: cliBlock }, configPath);
}

function resolveAuth(argv: string[]): DigichatCliAuth {
  const embedToken =
    readFlag(argv, "--embed-token") ||
    process.env.DIGICHAT_EMBED_TOKEN?.trim();
  if (embedToken) {
    return {
      kind: "embed",
      token: embedToken,
      host:
        readFlag(argv, "--embed-host") ||
        process.env.DIGICHAT_EMBED_HOST?.trim(),
    };
  }
  const apiKey =
    readFlag(argv, "--api-key") || process.env.DIGICHAT_API_KEY?.trim();
  if (apiKey) return { kind: "api_key", apiKey };
  return { kind: "none" };
}

function main(): void {
  const argv = process.argv.slice(2);
  if (argv.includes("--help") || argv.includes("-h")) {
    process.stdout.write(`digichat cli — Ink TTY client (assistant-ui react-ink)

Usage:
  digichat --url http://127.0.0.1:3005 [--config path/to/digichat.yaml]
  digichat --demo

Auth (one of, live mode):
  --embed-token / DIGICHAT_EMBED_TOKEN
  --api-key     / DIGICHAT_API_KEY

--demo runs the official with-react-ink scripted agent (no BFF).
When --config / DIGICHAT_CONFIG is set, cli.enabled must be true.
`);
    process.exit(0);
  }

  if (argv.includes("--demo")) {
    render(<DigichatCliApp mode="demo" />);
    return;
  }

  loadConfigIfRequested(argv);

  const baseUrl =
    readFlag(argv, "--url") ||
    process.env.DIGICHAT_URL?.trim() ||
    "http://127.0.0.1:3005";
  const model =
    readFlag(argv, "--model") || process.env.DIGICHAT_MODEL?.trim();

  render(
    <DigichatCliApp
      mode="live"
      modelName={model || "digigraph"}
      request={{
        baseUrl,
        auth: resolveAuth(argv),
        language:
          readFlag(argv, "--language") || process.env.DIGICHAT_LANGUAGE?.trim(),
        model,
        sessionId: `cli-${Date.now().toString(36)}`,
      }}
    />,
  );
}

main();
