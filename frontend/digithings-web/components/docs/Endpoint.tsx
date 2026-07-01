import type { Endpoint, Field } from "@/lib/apiDocs";
import { CodeTabs } from "./CodeTabs";

function FieldTable({ title, fields }: { title: string; fields: Field[] }) {
  return (
    <div className="doc-fieldset">
      <span className="doc-fieldset-h">{title}</span>
      <table className="doc-fields">
        <tbody>
          {fields.map((f) => (
            <tr key={f.name}>
              <td className="doc-f-name">
                <code className="dc-code-inline">{f.name}</code>
                {f.required && <span className="doc-req" title="required">*</span>}
              </td>
              <td className="doc-f-type">{f.type}</td>
              <td className="doc-f-desc">{f.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** One HTTP endpoint: method pill + path, summary, badges, request/response, examples. */
export function EndpointDoc({ ep }: { ep: Endpoint }) {
  return (
    <div className="doc-endpoint">
      <div className="doc-ep-head">
        <span className={`doc-method ${ep.method.toLowerCase()}`}>{ep.method}</span>
        <code className="doc-ep-path">{ep.path}</code>
      </div>
      <p className="doc-summary">{ep.summary}</p>
      <div className="doc-ep-badges">
        {ep.auth && <span className="doc-badge">auth · {ep.auth}</span>}
        {ep.rateLimit && <span className="doc-badge">{ep.rateLimit}</span>}
        {ep.flag && <span className="doc-badge is-road">{ep.flag}</span>}
      </div>
      {ep.request && ep.request.length > 0 && <FieldTable title="Request" fields={ep.request} />}
      {ep.responseFields && ep.responseFields.length > 0 && <FieldTable title="Response" fields={ep.responseFields} />}
      {ep.responseExample && (
        <div className="doc-fieldset">
          <span className="doc-fieldset-h">Response</span>
          <div className="doc-code">
            <pre>
              <code>{ep.responseExample}</code>
            </pre>
          </div>
        </div>
      )}
      {ep.examples && ep.examples.length > 0 && <CodeTabs examples={ep.examples} />}
    </div>
  );
}
