import { TriangleAlert } from "lucide-react";
import { api } from "../api/client";
import { Query } from "../components/Query";
import { SourceIcon } from "../components/sources";
import { useCaseView } from "../hooks";
import { usePanel } from "../panel";
import { useCaseContext } from "./CaseLayout";

export function Timeline() {
  const c = useCaseContext();
  const q = useCaseView(c.id, "timeline", api.timeline);
  const { openDocument } = usePanel();
  return (
    <Query q={q}>
      {({ events }) => events.length === 0 ? <div className="empty">No dated evidence yet.</div> : (
        <ol className="stack" style={{ listStyle: "none", padding: 0, margin: 0, gap: 6 }}>
          {events.map((e, i) => (
            <li key={i} className={`row ${e.type === "rewrite" ? "alert warn" : ""}`} style={{ alignItems: "baseline" }}
                data-testid={`event-${e.type}`}>
              <span className="mono small" style={{ minWidth: 88 }}>{e.date.slice(0, 10)}</span>
              {e.type === "document" && (
                <span className="row" style={{ gap: 6 }}>
                  <SourceIcon kind={e.source!.kind} />
                  <button className="chip" onClick={() => openDocument(e.doc_id!)}>{e.doc_id}</button>
                  <span className="small">{e.source!.publisher}</span>
                  {e.seen_late && <span className="badge s-warn" title="First seen long after the date it claims">first seen {e.first_seen!.slice(0, 10)}</span>}
                </span>
              )}
              {e.type === "claimed_event" && <span><b>Event in the claim</b> (<span className="mono">{e.subclaim_id}</span>): {e.text}</span>}
              {e.type === "rewrite" && (
                <span className="row" style={{ gap: 6 }}><TriangleAlert size={14} /><b>Rewritten version observed</b>
                  <button className="chip" onClick={() => openDocument(e.doc_id!)}>{e.doc_id}</button>
                  differs from <span className="mono">{e.earlier_doc_id}</span>: {e.text}
                  {e.needs_review && <span className="faint">(OCR: verify against the scan)</span>}</span>
              )}
            </li>
          ))}
        </ol>
      )}
    </Query>
  );
}
