"use client";
import type { ChatActivity } from "@/lib/chatStream";

function ActivityRow({ activity }: { activity: ChatActivity }) {
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
    default:
      return null;
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

export function ChatActivities({ activities }: { activities?: ChatActivity[] }) {
  if (!activities?.length) return null;
  return (
    <div className="dc-activities" aria-label="Agent steps">
      {activities.map((a, i) => (
        <ActivityRow key={`${a.kind}-${i}`} activity={a} />
      ))}
    </div>
  );
}
