import { useState } from "react";
import { api } from "../api/client";
import type { EvidenceItem } from "../api/types";
import { Chip } from "../components/Chip";
import { Query } from "../components/Query";
import { formatTnd, SourceIcon } from "../components/sources";
import { StatusBadge } from "../components/status";
import { useCaseView } from "../hooks";
import { useCaseContext } from "./CaseLayout";

function what(e: EvidenceItem): string {
  if (e.type === "quote") return `« ${e.quote} »`;
  if (e.type === "amount") return `${formatTnd(e.amount_tnd!)} (${e.role})`;
  return `nothing in ${e.register_name?.split(":")[0]} for « ${e.query} »`;
}

export function Evidence() {
  const c = useCaseContext();
  const q = useCaseView(c.id, "evidence", api.evidence);
  const [filter, setFilter] = useState("all");
  return (
    <Query q={q}>
      {({ items }) => {
        const shown = items.filter((e) => filter === "all" || (filter === "counts" ? e.counts : e.status === filter));
        return (
          <div className="stack">
            <div className="row small">
              <span className="muted">{items.filter((e) => e.counts).length} item(s) count; {items.filter((e) => e.status === "pending").length} pending review</span>
              <span className="spacer" />
              <select className="input" style={{ width: "auto" }} value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter">
                <option value="all">all</option><option value="counts">counts</option>
                <option value="pending">pending review</option><option value="disputed">disputed</option>
              </select>
            </div>
            <div className="table-wrap"><table>
              <thead><tr><th>Id</th><th>Sub-claim</th><th>Evidence</th><th>Source</th><th>Weight</th><th>Review</th></tr></thead>
              <tbody>{shown.map((e, i) => (
                <tr key={e.evidence_id ?? e.proposal_id ?? i}>
                  <td>{e.evidence_id ? <Chip id={e.evidence_id} /> : <span className="chip missing">{e.proposal_id}</span>}</td>
                  <td className="small">{e.subclaim_id && <><span className="mono">{e.subclaim_id}</span> {e.relation}</>}</td>
                  <td style={{ maxWidth: 420 }}>{what(e)}
                    {e.publisher_interest === "self_serving" && <span className="badge s-neutral" style={{ marginLeft: 6 }}>party</span>}
                    {e.publisher_interest === "against_interest" && <span className="badge s-neutral" style={{ marginLeft: 6 }}>concession</span>}</td>
                  <td className="small">
                    <span className="row" style={{ gap: 4 }}><SourceIcon kind={e.source?.kind ?? e.type} />
                      {e.source ? e.source.publisher : e.register}</span>
                    {e.source && <span className="faint">{e.source.reliability}</span>}
                  </td>
                  <td className="small">{e.weight != null ? e.weight.toFixed(2) : "–"}</td>
                  <td className="small"><StatusBadge status={e.status} />{e.review_note && <div className="faint">{e.review_note}</div>}</td>
                </tr>))}
              </tbody></table></div>
          </div>
        );
      }}
    </Query>
  );
}
