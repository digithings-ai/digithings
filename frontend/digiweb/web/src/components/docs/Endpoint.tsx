import { CodeTabs, DocsCodeBlock, type CodeSample } from "./CodeTabs";

/**
 * One HTTP endpoint as doc chrome: method chip + path, summary, metadata
 * badges, request/response field tables, and tabbed code samples.
 * Presentation-generic — the endpoint arrives fully described as props.
 * Method chips consume the theme-aware var(--method-*) custom props defined
 * in styles/docs.css (never raw hex at the use site); the field-table row
 * hairlines live there too.
 */

export type DocsMethod = "GET" | "POST" | "PUT" | "DELETE";

export interface DocsField {
  name: string;
  type: string;
  required?: boolean;
  description: string;
}

export interface DocsEndpoint {
  method: DocsMethod;
  path: string;
  summary: string;
  /** Auth requirement, e.g. "none", "bearer · orders:write". */
  auth?: string;
  /** Rate limit note, e.g. "10/min/IP". */
  rateLimit?: string;
  /** Flag / gate note — rendered muted, e.g. an env toggle. */
  flag?: string;
  request?: DocsField[];
  responseFields?: DocsField[];
  /** JSON string, when a shape reads clearer than a table. */
  responseExample?: string;
  examples?: CodeSample[];
}

const METHOD_BG: Record<DocsMethod, string> = {
  GET: "bg-(--method-get)",
  POST: "bg-(--method-post)",
  PUT: "bg-(--method-put)",
  DELETE: "bg-(--method-delete)",
};

/** The colored HTTP-method chip, on its own for legends and indexes. */
export function MethodBadge({ method }: { method: DocsMethod }) {
  return (
    <span
      className={`rounded-[6px] px-[0.45rem] py-[0.15rem] font-mono text-[0.7rem] font-semibold tracking-[0.04em] text-on-accent ${METHOD_BG[method]}`}
    >
      {method}
    </span>
  );
}

function InlineCode({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded-[5px] bg-ink/9 px-[0.3rem] py-[0.05rem] font-mono text-[0.82em]">
      {children}
    </code>
  );
}

function FieldTable({ title, fields }: { title: string; fields: DocsField[] }) {
  return (
    <div className="flex flex-col gap-[0.3rem]">
      <span className="font-mono text-[0.66rem] uppercase tracking-[0.12em] text-ink-mute">
        {title}
      </span>
      <table className="doc-fields w-full border-collapse text-[0.84rem]">
        <tbody>
          {fields.map((f) => (
            <tr key={f.name}>
              <td className="whitespace-nowrap">
                <InlineCode>{f.name}</InlineCode>
                {f.required && (
                  <span className="ml-[0.15rem] text-down" title="required">
                    *
                  </span>
                )}
              </td>
              <td className="whitespace-nowrap font-mono text-[0.78rem] text-ink-mute">{f.type}</td>
              <td className="w-full leading-[1.5] text-ink-soft">{f.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Small bordered metadata chip beside the endpoint head. */
function DocBadge({ muted, children }: { muted?: boolean; children: React.ReactNode }) {
  return (
    <span
      className={`whitespace-nowrap rounded-[7px] border border-hair px-[0.45rem] py-[0.15rem] font-mono text-[0.68rem] ${
        muted ? "text-ink-mute" : "text-ink-soft"
      }`}
    >
      {children}
    </span>
  );
}

export function EndpointDoc({ ep }: { ep: DocsEndpoint }) {
  return (
    <div className="doc-endpoint flex flex-col gap-[0.55rem] rounded-[12px] border border-hair bg-surface/55 p-[clamp(0.8rem,2vw,1.1rem)]">
      <div className="flex flex-wrap items-center gap-[0.6rem]">
        <MethodBadge method={ep.method} />
        <code className="break-all font-mono text-[0.92rem] text-ink">{ep.path}</code>
      </div>
      <p className="m-0 text-[0.88rem] leading-[1.65] text-ink-soft">{ep.summary}</p>
      {(ep.auth || ep.rateLimit || ep.flag) && (
        <div className="flex flex-wrap gap-[0.35rem]">
          {ep.auth && <DocBadge>auth · {ep.auth}</DocBadge>}
          {ep.rateLimit && <DocBadge>{ep.rateLimit}</DocBadge>}
          {ep.flag && <DocBadge muted>{ep.flag}</DocBadge>}
        </div>
      )}
      {ep.request && ep.request.length > 0 && <FieldTable title="Request" fields={ep.request} />}
      {ep.responseFields && ep.responseFields.length > 0 && (
        <FieldTable title="Response" fields={ep.responseFields} />
      )}
      {ep.responseExample && (
        <div className="flex flex-col gap-[0.3rem]">
          <span className="font-mono text-[0.66rem] uppercase tracking-[0.12em] text-ink-mute">
            Response
          </span>
          <DocsCodeBlock code={ep.responseExample} copyLabel="Copy response example" />
        </div>
      )}
      {ep.examples && ep.examples.length > 0 && <CodeTabs samples={ep.examples} />}
    </div>
  );
}
