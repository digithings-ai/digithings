/**
 * Empty / error states — the outcomes the skeleton loader resolves into when
 * there's nothing to show: no results, a first-run blank, and a load error.
 * Each is a centered card — glyph, title, one line of guidance, and the single
 * action that moves the user forward. Monochrome by default; the error reserves
 * the down colour. Static display templates. Consumes the shared <EmptyState/>
 * primitive from @digithings/ui (each variant carries its default glyph).
 *
 * Also shows the `glass-display` cut — the dashboard's full-page DB gate. That
 * dress is fluid (`w-full`) and wrap-safe (`break-words`) so the gate cannot
 * clip its own message at phone width (#4452).
 */
import { EmptyState, type EmptyStateVariant } from "@digithings/ui/ui";
import { Button } from "@digithings/ui/ui";

const STATES: {
  id: EmptyStateVariant;
  title: string;
  msg: string;
  action: string;
  primary?: boolean;
}[] = [
  {
    id: "no-results",
    title: "No strategies match",
    msg: "Nothing fits those filters. Broaden the query or clear a tag or two.",
    action: "Clear filters",
  },
  {
    id: "first-run",
    title: "Nothing here yet",
    msg: "Run your first backtest and its tearsheet will land in the vault.",
    action: "New backtest",
    primary: true,
  },
  {
    id: "error",
    title: "Couldn't load positions",
    msg: "The venue feed timed out. Retry, or check the status page.",
    action: "Retry",
  },
];

export function EmptyStatesReference() {
  return (
    <section className="section-block">
      <p className="kicker">{"// empty & error states"}</p>
      <h2 className="title">When there&apos;s nothing to show.</h2>
      <p className="section-copy">
        The states the skeleton resolves into — no results, a first-run blank, a load error — each a
        centered card with a glyph, a title, one line of guidance, and the single action that moves
        forward. The error is the only one that spends the down color.
      </p>

      <div className="mt-[1.2rem] grid grid-cols-3 gap-[0.9rem] max-[720px]:grid-cols-1">
        {STATES.map((s) => (
          <EmptyState
            key={s.id}
            variant={s.id}
            title={s.title}
            body={s.msg}
            action={<Button variant={s.primary ? "default" : "ghost"}>{s.action}</Button>}
          />
        ))}
      </div>

      {/* The dashboard's full-page gate cut (`dress="glass-display"`). Rendered
          here because it is the honesty surface an operator sees when live data
          is unreachable — and it must stay fluid and wrap-safe at phone widths
          (#4452), so the reference shows the real copy at its call-site cap. */}
      <p className="kicker mt-[2rem]">{"// glass-display — the full-page gate"}</p>
      <EmptyState
        variant="error"
        dress="glass-display"
        className="mx-auto max-w-md"
        title="Live data is not connected in this build"
        body="This deployment has no live data backend configured, so live figures cannot load. Static surfaces — Pipeline and Settings — stay available."
        action={<Button variant="outline">Retry</Button>}
      />
    </section>
  );
}
