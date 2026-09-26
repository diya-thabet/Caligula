import { api } from "../api/client";
import { Query } from "../components/Query";
import { SourceIcon } from "../components/sources";
import { useCaseView } from "../hooks";
import { usePanel } from "../panel";
import { useCaseContext } from "./CaseLayout";

export function Documents() {
  const c = useCaseContext();
  const q = useCaseView(c.id, "documents", api.documents);
  const { openDocument } = usePanel();
  return (
    <Query q={q}>
      {({ documents }) => (
        <div className="table-wrap"><table>
          <thead><tr><th>Document</th><th>Source</th><th>Published / seen</th><th>Custody</th><th>Used by</th></tr></thead>
          <tbody>{documents.map((d) => (
            <tr key={d.doc_id}>
              <td><button className="chip" onClick={() => openDocument(d.doc_id)}>{d.doc_id}</button>
                {d.title && <div className="small">{d.title}</div>}</td>
              <td className="small"><span className="row" style={{ gap: 4 }}><SourceIcon kind={d.kind} />{d.publisher}</span>
                <span className="faint">{d.reliability}</span></td>
              <td className="small">{d.published_at?.slice(0, 10) ?? "–"} / {d.observed_at.slice(0, 10)}</td>
              <td className="small">{d.custody.bytes_intact ? "bytes intact" : <span className="error-text">hash mismatch</span>}
                <div className="hash">{d.custody.raw_sha256.slice(0, 16)}…</div>
                <div className="faint">{d.custody.extraction}</div></td>
              <td className="small mono">{d.used_by.join(", ") || "–"}</td>
            </tr>))}
          </tbody></table></div>
      )}
    </Query>
  );
}
