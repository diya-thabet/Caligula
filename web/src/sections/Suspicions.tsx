import { api } from "../api/client";
import { Checkpoint } from "../components/Checkpoint";
import { Query } from "../components/Query";
import { StatusBadge } from "../components/status";
import { useCaseView } from "../hooks";
import { useCaseContext } from "./CaseLayout";

export function Suspicions() {
  const c = useCaseContext();
  const q = useCaseView(c.id, "suspicions", api.suspicions);
  return (
    <Query q={q}>
      {({ suspicions }) => suspicions.length === 0 ? (
        <div className="empty">The reviewer raised no suspicion in this case.</div>
      ) : (
        <div className="stack">
          <div className="faint">Each suspicion is tested both ways, one task to confirm it and one to refute it; its status
            follows the evidence on the sub-claim that states it, never the reviewer's opinion.</div>
          {suspicions.map((s) => (
            <article key={s.id} className={`card stack ${s.status === "awaiting_scope" ? "pending" : ""}`} style={{ gap: 6 }}
                     data-testid={`suspicion-${s.id}`}>
              <div className="row">
                <span className="mono">{s.id}</span><StatusBadge status={s.status} />
                <span className="faint">raised by {s.raised_by} in round {s.round}
                  {s.resolved_round ? `, settled in round ${s.resolved_round}` : ""}</span>
              </div>
              <div style={{ fontWeight: 500 }}>{s.statement}</div>
              <div className="grid-3 small">
                <div><div className="faint">Would confirm it</div>{s.confirm_by}</div>
                <div><div className="faint">Would refute it</div>{s.refute_by}</div>
                <div><div className="faint">Tested by</div>
                  {s.tested_by ? <span className="mono">{s.tested_by}</span> : "–"}{s.tasks.length > 0 && <> · tasks <span className="mono">{s.tasks.join(", ")}</span></>}</div>
              </div>
              {s.note && <div className="faint">{s.note}</div>}
              {s.status === "awaiting_scope" && (
                <Checkpoint caseId={c.id} title={`Wider scope: ${s.id}`} role="lawyer" actions={[
                  { label: "Approve the wider scope", primary: true, run: (note) => api.decideScope(c.id, s.id, true, note) },
                  { label: "Reject", danger: true, run: (note) => api.decideScope(c.id, s.id, false, note) },
                ]}>
                  This suspicion brings in people or companies outside the case: <b>{s.new_entities.join(", ")}</b>.
                  Approved, specialists look both ways in the next round; rejected, nobody investigates it.
                </Checkpoint>
              )}
            </article>
          ))}
        </div>
      )}
    </Query>
  );
}
