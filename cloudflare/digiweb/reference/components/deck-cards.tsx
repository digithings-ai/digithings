/**
 * Presentational card variants rendered inside CardDeck items — a metric
 * summary, a changelog, a pull-quote, and an alert. Each is content-only: the
 * deck owns positioning, stacking, and the rail, so these just lay out their
 * own body and wear the up / down colours where P&L applies. Static display
 * templates.
 */

type MetricCardProps = {
  name: string;
  summary: string;
  ordinal: number | string;
  cagr: string;
  maxDd: string;
  pf: string;
};

export function MetricCard({ name, summary, ordinal, cagr, maxDd, pf }: MetricCardProps) {
  return (
    <>
      <div className="deck-card-head">
        <h3>{name}</h3>
        <span>{ordinal}</span>
      </div>
      <p>{summary}</p>
      <dl>
        <div>
          <dt>CAGR</dt>
          <dd className="up">{cagr}</dd>
        </div>
        <div>
          <dt>Max DD</dt>
          <dd className="down">{maxDd}</dd>
        </div>
        <div>
          <dt>Profit factor</dt>
          <dd>{pf}</dd>
        </div>
      </dl>
    </>
  );
}

type ChangelogCardProps = {
  version: string;
  date: string;
  entries: string[];
};

export function ChangelogCard({ version, date, entries }: ChangelogCardProps) {
  return (
    <div className="deck-changelog">
      <div className="deck-card-head">
        <h3 className="deck-changelog-version">{version}</h3>
        <span>{date}</span>
      </div>
      <ul>
        {entries.map((entry) => (
          <li key={entry}>{entry}</li>
        ))}
      </ul>
    </div>
  );
}

type QuoteCardProps = {
  quote: string;
  attribution: string;
};

export function QuoteCard({ quote, attribution }: QuoteCardProps) {
  return (
    <figure className="deck-quote">
      <blockquote>{quote}</blockquote>
      <figcaption>{attribution}</figcaption>
    </figure>
  );
}

type AlertCardProps = {
  status: string;
  tone: "up" | "down";
  timestamp: string;
  title: string;
  impact: string;
};

export function AlertCard({ status, tone, timestamp, title, impact }: AlertCardProps) {
  return (
    <div className="deck-alert">
      <div className={`deck-alert-status ${tone}`}>
        <span className="deck-alert-dot" aria-hidden="true" />
        <span>{status}</span>
        <span className="deck-alert-time">{timestamp}</span>
      </div>
      <h3>{title}</h3>
      <p>{impact}</p>
    </div>
  );
}
