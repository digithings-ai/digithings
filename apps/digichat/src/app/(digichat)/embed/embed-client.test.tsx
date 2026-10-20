// @vitest-environment happy-dom
/**
 * Trial proof presenter (DIG-4523).
 *
 * The embedding page hands over a server-signed, host-scoped trial proof over
 * postMessage. The client holds it in memory only and reads it at send time.
 *
 * Two things are pinned here:
 *   1. the message gate — a proof is only taken from the origin we serve, and
 *      never for another host;
 *   2. the in-memory-only rule — the proof never reaches storage and never
 *      reaches a URL.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  embedParentOrigin,
  readTrialProofMessage,
  TRIAL_PROOF_MESSAGE_TYPE,
} from "./embed-client";

const embedClientSrc = readFileSync(join(__dirname, "embed-client.tsx"), "utf8");

/** Code lines only — comments state the rule, they do not implement it. */
function codeLinesOf(source: string): string[] {
  return source
    .split("\n")
    .filter((line) => {
      const trimmed = line.trim();
      return (
        trimmed.length > 0 &&
        !trimmed.startsWith("//") &&
        !trimmed.startsWith("*") &&
        !trimmed.startsWith("/*")
      );
    });
}

const proofCodeLines = codeLinesOf(embedClientSrc).filter((line) =>
  /trialProof|getTrialProof|TRIAL_PROOF|trial:proof/.test(line),
);

describe("embed parent origin", () => {
  it("derives the origin of the page that embeds us", () => {
    expect(embedParentOrigin("https://tenant.example")).toBe("https://tenant.example");
    expect(embedParentOrigin("tenant.example")).toBe("https://tenant.example");
  });

  it("drops the path when the host is given as a full URL", () => {
    expect(embedParentOrigin("https://tenant.example/chat?a=1")).toBe(
      "https://tenant.example",
    );
  });

  it("has no origin when no host is served", () => {
    expect(embedParentOrigin(undefined)).toBeNull();
    expect(embedParentOrigin("   ")).toBeNull();
  });
});

describe("readTrialProofMessage", () => {
  const options = {
    parentOrigin: "https://tenant.example",
    servingHost: "https://tenant.example",
  };

  it("takes the proof from the origin we serve", () => {
    const proof = readTrialProofMessage(
      {
        origin: "https://tenant.example",
        data: { type: TRIAL_PROOF_MESSAGE_TYPE, proof: "hmac.trial.proof" },
      },
      options,
    );
    expect(proof).toBe("hmac.trial.proof");
  });

  it("ignores a proof posted from another origin", () => {
    const proof = readTrialProofMessage(
      {
        origin: "https://evil.example",
        data: { type: TRIAL_PROOF_MESSAGE_TYPE, proof: "hmac.trial.proof" },
      },
      options,
    );
    expect(proof).toBeNull();
  });

  it("ignores a message of another type", () => {
    const proof = readTrialProofMessage(
      {
        origin: "https://tenant.example",
        data: { type: "digichat:plan-tier", proof: "hmac.trial.proof" },
      },
      options,
    );
    expect(proof).toBeNull();
  });

  it("ignores an empty proof", () => {
    const proof = readTrialProofMessage(
      {
        origin: "https://tenant.example",
        data: { type: TRIAL_PROOF_MESSAGE_TYPE, proof: "   " },
      },
      options,
    );
    expect(proof).toBeNull();
  });

  it("rejects a proof sent under another field name", () => {
    const proof = readTrialProofMessage(
      {
        origin: "https://tenant.example",
        data: { type: TRIAL_PROOF_MESSAGE_TYPE, token: "hmac.trial.proof" },
      },
      options,
    );
    expect(proof).toBeNull();
  });

  it("ignores a proof that names another host", () => {
    const proof = readTrialProofMessage(
      {
        origin: "https://tenant.example",
        data: {
          type: TRIAL_PROOF_MESSAGE_TYPE,
          proof: "hmac.trial.proof",
          host: "https://other.example",
        },
      },
      options,
    );
    expect(proof).toBeNull();
  });

  it("accepts a proof that names the host we serve in another spelling", () => {
    const proof = readTrialProofMessage(
      {
        origin: "https://tenant.example",
        data: {
          type: TRIAL_PROOF_MESSAGE_TYPE,
          proof: "hmac.trial.proof",
          host: "tenant.example",
        },
      },
      options,
    );
    expect(proof).toBe("hmac.trial.proof");
  });
});

describe("trial proof is held in memory only", () => {
  it("pins the code that carries the proof", () => {
    expect(proofCodeLines.length).toBeGreaterThan(0);
  });

  it("never writes the proof to storage", () => {
    for (const line of proofCodeLines) {
      expect(line).not.toMatch(/localStorage|sessionStorage|setItem|getItem|indexedDB/);
    }
  });

  it("never puts the proof in a URL", () => {
    for (const line of proofCodeLines) {
      expect(line).not.toMatch(/new URL\(|searchParams|href|location\.|URLSearchParams/);
    }
  });

  it("keeps the proof in a ref and reads it through a getter", () => {
    expect(embedClientSrc).toMatch(/useRef<string \| null>\(null\)/);
    expect(embedClientSrc).toMatch(/const getTrialProof = useCallback\(\(\) => trialProofRef\.current/);
    expect(embedClientSrc).toMatch(/getTrialProof,/);
  });

  it("never clears the proof on the unlock path", () => {
    // The page posts the proof before the unlock, so the proof is still
    // needed when the unlock arrives: no line that touches the proof may
    // be driven by the unlock.
    for (const line of proofCodeLines) {
      expect(line).not.toMatch(/unlock/i);
    }
  });

  it("uses a message type that names no client", () => {
    expect(TRIAL_PROOF_MESSAGE_TYPE).toBe("trial:proof");
  });
});
