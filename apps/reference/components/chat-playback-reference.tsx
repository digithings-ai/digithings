import { ChatPlayback, type ChatPlaybackStep } from "@digithings/ui";

/**
 * Chat playback — the specimen for the shared <ChatPlayback/> (@digithings/ui,
 * chat): a scripted chat simulation in a terminal frame. The script is data:
 * user prompts type out, tool-call rows run then settle (results can be masked
 * to `▒`), and the assistant text streams. It starts once when scrolled into
 * view, plays once, then offers [replay]; [pause] and [skip] are visible while
 * it runs. Reduced motion and no-JS show the full transcript statically; the
 * region is aria-live off with an sr-only full transcript. The badge is a
 * required prop and lives in the frame chrome. The tool names below are
 * obviously fictional sample values, not a real server's tools.
 */
const SAMPLE: ChatPlaybackStep[] = [
  { role: "user", text: "Which sample datasets are loaded?" },
  {
    role: "tool",
    tool: {
      name: "sample.list_datasets",
      args: "limit=3",
      result: {
        columns: ["dataset", "rows"],
        rows: [
          ["aaaa", "0000"],
          ["bbbb", "0000"],
          ["cccc", "0000"],
        ],
      },
      masked: true,
    },
  },
  { role: "assistant", text: "Three sample datasets came back. Their contents are masked in this simulation." },
  { role: "user", text: "Summarise the first one." },
  { role: "tool", tool: { name: "sample.describe", args: "dataset=aaaa", result: "field one: value\nfield two: value", masked: true } },
  { role: "assistant", text: "Here is where a summary would stream in. Nothing in this session ran anywhere." },
];

export function ChatPlaybackReference() {
  return (
    <section className="section-block" id="chat-playback">
      <p className="kicker">{"// chat playback"}</p>
      <h2 className="title">A scripted session that says it is scripted.</h2>
      <p className="section-copy">
        Scroll it into view and it types the prompt, runs the tool rows and streams the reply once.
        Pause, skip or replay from the title row. The badge inside the frame is mandatory, results
        can be masked, and with reduced motion the whole transcript is simply there.
      </p>
      <div className="mt-[1.2rem] max-w-[46rem]">
        <ChatPlayback
          script={SAMPLE}
          header="sample session"
          badge="Simulation · scripted · not connected to anything"
        />
      </div>
    </section>
  );
}
