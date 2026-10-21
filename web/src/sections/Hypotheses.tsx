import { api } from "../api/client";
import type { AchMatrix, HypothesisCard } from "../api/types";
import { Query } from "../components/Query";
import { StatusBadge } from "../components/status";
import { useCaseView } from "../hooks";
import { usePanel } from "../panel";
import { useCaseContext } from "./CaseLayout";

const CELL: Record<string, { label: string; title: string; className: string }> = {
  C: { label: "C", title: "consistent with this explanation", className: "" },
  I: { label: "I", title: "inconsistent: evidence against this explanation", className: "s-bad" },
  N: { label: "–", title: "this explanation predicts nothing here", className: "faint" },
};

function Matrix({ m, hyps }: { m: AchMatrix; hyps: Record<string, HypothesisCard> }) {
  const { openDocument } = usePanel();
  const rows = [...m.rows].sort((a, b) => Number(b.diagnostic) - Number(a.diagnostic) || a.subclaim_id.localeCompare(b.subclaim_id));
  const order = [...m.ranking, ...m.untested];
  return (
    <section className="stack" aria-label={`Matrix ${m.hypotheses.join(", ")}`}>
      <div className="stack" style={{ gap: 6 }}>
        {order.map((id, i) => {
          const h = hyps[id];
          return (
            <div key={id} className="card row" style={{ alignItems: "flex-start" }} data-testid={`hypothesis-${id}`}>
              <span className="mono" style={{ minWidth: 28 }}>{id}</span>
              <div className="stack" style={{ gap: 2, flex: 1 }}>
                <div className="row"><StatusBadge status={h.status} /><span className="badge s-neutral">{h.kind}</span>
                  {m.untested.includes(id) ? <span className="faint">untested: no evidence yet on what it predicts</span>
                    : <span className="faint">evidence against {m.inconsistency[id]?.toFixed(2)}{i === 0 ? " · least contradicted" : ""}</span>}
                </div>
                <div>{h.statement}</div>
                <div className="faint">{h.reasons.join("; ")}</div>
              </div>
            </div>
          );
        })}
      </div>
      {rows.length > 0 && (
        <div className="table-wrap"><table>
          <thead><tr><th>Evidence (one row per independent origin)</th><th>Weight</th>
            {m.hypotheses.map((h) => <th key={h} className="mono">{h}</th>)}</tr></thead>
          <tbody>{rows.map((r, i) => (
            <tr key={i}>
              <td className="small">{r.diagnostic && <span title="diagnostic: tells the explanations apart">◆ </span>}
                <span className="mono">{r.subclaim_id}</span> {r.relation}{" "}
                {r.doc_ids.map((d) => d.startsWith("absence:") || d === "financial-check"
                  ? <span key={d} className="mono faint">{d} </span>
                  : <button key={d} className="chip" onClick={() => openDocument(d)}>{d}</button>)}
              </td>
              <td className="small">{r.weight.toFixed(2)}</td>
              {m.hypotheses.map((h) => {
                const cell = CELL[r.ratings[h]];
                return <td key={h} title={cell.title}><span className={`badge ${cell.className}`}>{cell.label}</span></td>;
              })}
            </tr>))}
          </tbody></table></div>
      )}
    </section>
  );
}

export function Hypotheses() {
  const c = useCaseContext();
  const q = useCaseView(c.id, "claims", api.claims);
  return (
    <Query q={q}>
      {(view) => {
        const hyps = Object.fromEntries(view.hypotheses.map((h) => [h.id, h]));
        return (
          <div className="stack">
            <div className="faint">Ratings follow from each explanation's own predictions, computed by code. The least
              contradicted explanation leads, not the most supported; evidence that fits every explanation proves little (◆ marks
              evidence that tells them apart).</div>
            {(view.ach ?? []).filter((m) => m.hypotheses.length > 1).map((m) => <Matrix key={m.hypotheses.join()} m={m} hyps={hyps} />)}
            {view.ruled_out.length > 0 && (
              <section className="card small stack" style={{ gap: 4 }}>
                <b>Ruled out, with the reason given</b>
                {view.ruled_out.map((r) => <div key={r.explanation_id}><i>{r.explanation_id.replaceAll("_", " ")}</i>: {r.reason}</div>)}
              </section>
            )}
          </div>
        );
      }}
    </Query>
  );
}
