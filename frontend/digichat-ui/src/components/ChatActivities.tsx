"use client";

import type { DigiChatActivity } from "../types";

function ActivityRow({ activity }: { activity: DigiChatActivity }) {
  switch (activity.kind) {
    case "status":
      return <p className="dc-act-status">{activity.message}</p>;
    case "tool_call":
      return (
        <p className="dc-act-tool">
          <span className="dc-act-label">tool</span>{" "}
          <code className="dc-act-code">{activity.name}</code>
          <span className="dc-act-query"> — {activity.query}</span>
        </p>
      );
    case "tool_result":
      return (
        <div className="dc-act-result">
          <p className="dc-act-tool">
            <span className="dc-act-label">vault</span>{" "}
            {activity.count > 0
              ? `${activity.count} note${activity.count === 1 ? "" : "s"} for “${activity.query}”`
              : `no hits for “${activity.query}”`}
          </p>
          {activity.hits.length > 0 ? (
            <ul className="dc-act-hits">
              {activity.hits.map((h) => (
                <li key={h.path}>
                  <span className="dc-act-hit-title">{h.title}</span>
                  <span className="dc-act-hit-path">{h.path}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      );
    case "reasoning":
      return <ReasoningBlock text={activity.text} />;
    case "trace": {
      return (
        <p className={`dc-act-line${activity.done ? " is-done" : ""}`}>
          {activity.done ? <span className="dc-act-check">✓</span> : "…"} {activity.label}
        </p>
      );
    }
    default: {
      const _exhaustive: never = activity;
      void _exhaustive;
      return null;
    }
  }
}

function ReasoningBlock({ text }: { text: string }) {
  if (!text.trim()) return null;
  return (
    <details className="dc-act-reasoning">
      <summary>reasoning</summary>
      <pre>{text}</pre>
    </details>
  );
}

export function ChatActivities({ activities }: { activities?: DigiChatActivity[] }) {
  if (!activities?.length) return null;
  const hasTraces = activities.some((a) => a.kind === "trace");
  return (
    <div className={`dc-activities${hasTraces ? " dc-activities-traces" : ""}`} aria-label="Agent steps">
      {activities.map((a, i) => (
        <ActivityRow key={`${a.kind}-${i}`} activity={a} />
      ))}
    </div>
  );
}
