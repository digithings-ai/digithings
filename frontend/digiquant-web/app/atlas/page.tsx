"use client";
import { useEffect } from "react";

export default function AtlasRedirect() {
  useEffect(() => { location.replace("/subsystems/atlas/"); }, []);
  return (
    <main className="section">
      <div className="wrap" style={{ textAlign: "center" }}>
        <p style={{ fontFamily: "var(--font-mono)", color: "var(--ink-soft)" }}>
          Redirecting to <a href="/subsystems/atlas/" style={{ color: "var(--accent)" }}>the Atlas subsystem page</a>…
        </p>
      </div>
    </main>
  );
}
