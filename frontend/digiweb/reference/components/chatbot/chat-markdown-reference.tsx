/**
 * Chat markdown — an assistant turn rendering full markdown (headings, emphasis,
 * lists, block quotes, fenced code with a copy affordance, tables) on the token
 * palette. Consumes the shared chat-core primitives from @digithings/web
 * (<ChatTranscript>/<ChatMessage>/<ChatMarkdown>/<ChatCodeBlock>) — bare
 * markdown elements pick up the .chat-md grammar, no per-node classes. Static
 * display template.
 */
import { ChatCodeBlock, ChatMarkdown, ChatMessage, ChatTranscript } from "@digithings/web";

const SNIPPET = `bt = Backtest("trend_xsec", symbol="ETH-USD")
bt.fees = venue.schedule("binance")
bt.sizing = Kelly(cap=0.5)
report = bt.run(years=8)`;

export function ChatMarkdownReference() {
  return (
    <section className="section-block">
      <p className="kicker">{"// markdown"}</p>
      <h2 className="title">Rich text, rendered in place.</h2>
      <p className="section-copy">
        Assistant turns render full markdown — headings, emphasis, ordered and unordered lists,
        block quotes, fenced code with a copy affordance, and tables — all on the token palette so
        it reads as one surface. This shows the rendered result, not the raw source.
      </p>

      <ChatTranscript
        session="digichat — session"
        className="mt-[1.3rem] max-w-[760px] gap-[0.7rem]"
      >
        <ChatMessage role="assistant" className="text-[0.86rem] leading-[1.5]">
          <ChatMarkdown>
            <h3>Backtest summary</h3>
            <p>
              <code>trend_xsec</code> on <strong>ETH-USD</strong> over eight years returns a{" "}
              <strong>profit factor of 2.31</strong> — <em>respectable, but fee-sensitive</em>. Two
              things worth calling out before you size it up:
            </p>
            <ul>
              <li>Turnover is high — half the edge is eaten below 4bps of slippage.</li>
              <li>The 2022 drawdown ran 11 weeks; size for the duration, not just the depth.</li>
            </ul>
            <p>Suggested next steps:</p>
            <ol>
              <li>Re-run with the venue&apos;s live maker/taker schedule.</li>
              <li>Add a volatility target so exposure scales down in chop.</li>
              <li>Paper-trade for two weeks before any live capital.</li>
            </ol>
            <blockquote>
              Never route to a broker without human approval — live paths are gated for a reason.
            </blockquote>
            <ChatCodeBlock code={SNIPPET} lang="python" />
            <table>
              <thead>
                <tr>
                  <th>metric</th>
                  <th>value</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>profit factor</td>
                  <td>2.31</td>
                </tr>
                <tr>
                  <td>max drawdown</td>
                  <td>−18.4%</td>
                </tr>
                <tr>
                  <td>sharpe</td>
                  <td>1.87</td>
                </tr>
              </tbody>
            </table>
            <p>
              Full methodology in the <a href="#">vault tearsheet</a>.
            </p>
          </ChatMarkdown>
        </ChatMessage>
      </ChatTranscript>
    </section>
  );
}
