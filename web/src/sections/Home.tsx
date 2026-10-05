import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Inbox, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { QueueItem } from "../api/types";
import { ago, Query } from "../components/Query";
import { CaseStatusBadge, ConfidenceMeter, VerdictBadge } from "../components/status";
import { useUser } from "../hooks";

export const APPROVAL_TARGET: Record<QueueItem["kind"], string> = {
  legal_review: "",
  plan_approval: "plan",
  scope: "suspicions",
  sign_off: "casefile",
};

const APPROVAL_LABEL: Record<QueueItem["kind"], string> = {
  legal_review: "Legal review of the claim",
  plan_approval: "Plan approval",
  scope: "Wider scope",
  sign_off: "Sign-off",
};

function NewCase({ canInvestigate }: { canInvestigate: boolean }) {
  const [user] = useUser();
  const [claim, setClaim] = useState("");
  const [mode, setMode] = useState("investigate");
  const [poc, setPoc] = useState(true);
  const navigate = useNavigate();
  const client = useQueryClient();
  const open = useMutation({
    mutationFn: () => api.openCase(claim, mode, poc),
    onSuccess: (c) => {
      client.invalidateQueries({ queryKey: ["cases"] });
      navigate(`/cases/${encodeURIComponent(c.id)}`);
    },
  });
  const blocked = !canInvestigate ? "No model is configured on the server: new cases cannot be investigated. "
    + "Replayed cases below stay open for review." : !user ? "Say who you are (top right) first: it goes to the ledger." : null;
  return (
    <form className="card stack" onSubmit={(e) => { e.preventDefault(); open.mutate(); }}>
      <h2>New case</h2>
      <label className="field">
        <span className="muted">Describe the claim to investigate (French, English or Arabic)</span>
        <textarea rows={3} value={claim} onChange={(e) => setClaim(e.target.value)} disabled={!canInvestigate}
                  placeholder="Le marché 2026-017 a été attribué sans appel d'offres…" />
      </label>
      <div className="row">
        <label className="row small">Mode
          <select className="input" style={{ width: "auto" }} value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="investigate">Investigation</option>
            <option value="factcheck">Fact-check</option>
          </select>
        </label>
        <label className="row small" title="Cases needing legal review proceed, marked internal and not for publication">
          <input type="checkbox" checked={poc} onChange={(e) => setPoc(e.target.checked)} /> Proof of concept (internal only)
        </label>
        <span className="spacer" />
        <button className="btn primary" type="submit" disabled={!!blocked || !claim.trim() || open.isPending}>
          <Plus size={14} /> Open case
        </button>
      </div>
      {blocked && <div className="faint">{blocked}</div>}
      {open.isError && <div className="error-text" role="alert">{(open.error as Error).message}</div>}
    </form>
  );
}

export function Home() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.cases, refetchInterval: 5000 });
  const approvals = useQuery({ queryKey: ["approvals"], queryFn: api.approvals, refetchInterval: 5000 });
  return (
    <main className="centre">
      <div className="page stack">
        <NewCase canInvestigate={health.data?.can_investigate ?? false} />
        <section className="stack" aria-labelledby="attention">
          <h2 id="attention" className="row"><Inbox size={16} /> Needs attention</h2>
          <Query q={approvals}>
            {(items) => items.length === 0 ? <div className="faint">Nothing waits for a person.</div> : (
              <div className="table-wrap"><table>
                <thead><tr><th>Case</th><th>Waiting for</th><th>Role</th><th>About</th></tr></thead>
                <tbody>{items.map((a, i) => (
                  <tr key={i}>
                    <td><Link className="mono" to={`/cases/${encodeURIComponent(a.case_id)}/${APPROVAL_TARGET[a.kind]}`}>{a.case_id}</Link></td>
                    <td>{APPROVAL_LABEL[a.kind]}</td><td>{a.role}</td><td className="muted">{a.about}</td>
                  </tr>))}
                </tbody></table></div>
            )}
          </Query>
        </section>
        <section className="stack" aria-labelledby="cases">
          <h2 id="cases">Cases</h2>
          <Query q={cases}>
            {(list) => list.length === 0 ? (
              <div className="empty">No case yet. Describe a claim above, or start the server with
                <span className="mono"> --replay fixtures/steg_synthetic</span> to review the synthetic case.</div>
            ) : (
              <div className="table-wrap"><table>
                <thead><tr><th>Case</th><th>Claim</th><th>Status</th><th>Assessment</th><th>Last activity</th></tr></thead>
                <tbody>{list.map((c) => (
                  <tr key={c.id}>
                    <td><Link className="mono" to={`/cases/${encodeURIComponent(c.id)}`}>{c.id}</Link></td>
                    <td style={{ maxWidth: 420 }}>{c.title}</td>
                    <td><CaseStatusBadge status={c.status} /></td>
                    <td>{c.assessment ? (
                      <span className="stack" style={{ gap: 2 }}>
                        <VerdictBadge verdict={c.assessment.verdict} />
                        <span className="small muted">{c.assessment.likelihood_term} · <ConfidenceMeter level={c.assessment.confidence} /></span>
                      </span>) : <span className="faint">not yet</span>}</td>
                    <td className="small muted">{ago(c.last_activity)}</td>
                  </tr>))}
                </tbody></table></div>
            )}
          </Query>
        </section>
      </div>
    </main>
  );
}
