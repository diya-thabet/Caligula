import { Download } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import { Query } from "../components/Query";
import { useCaseView } from "../hooks";
import { useCaseContext } from "./CaseLayout";

export function Audit() {
  const c = useCaseContext();
  const q = useCaseView(c.id, "audit", api.audit);
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  return (
    <Query q={q}>
      {(log) => {
        const actions = [...new Set(log.entries.map((e) => e.action))].sort();
        const actors = [...new Set(log.entries.map((e) => e.actor))].sort();
        const shown = log.entries.filter((e) => (!action || e.action === action) && (!actor || e.actor === actor));
        return (
          <div className="stack">
            <div className={`alert ${log.integrity.intact ? "info" : "bad"}`} data-testid="integrity">
              {log.integrity.intact ? <>Chain intact: {log.integrity.entries} entries, head{" "}
                <span className="hash">{log.integrity.head.slice(0, 16)}…</span></>
                : <b>Chain broken at entry {log.integrity.broken_at}: the record was altered after it was written.</b>}
            </div>
            <div className="row small">
              <select className="input" style={{ width: "auto" }} value={action} onChange={(e) => setAction(e.target.value)} aria-label="Action">
                <option value="">every action</option>{actions.map((a) => <option key={a}>{a}</option>)}
              </select>
              <select className="input" style={{ width: "auto" }} value={actor} onChange={(e) => setActor(e.target.value)} aria-label="Actor">
                <option value="">everyone</option>{actors.map((a) => <option key={a}>{a}</option>)}
              </select>
              <span className="spacer" />
              <button className="btn" onClick={() => {
                const url = URL.createObjectURL(new Blob([JSON.stringify(log, null, 1)], { type: "application/json" }));
                Object.assign(document.createElement("a"), { href: url, download: `${c.id}-ledger.json` }).click();
                URL.revokeObjectURL(url);
              }}><Download size={14} /> Export</button>
            </div>
            <div className="table-wrap"><table>
              <thead><tr><th>#</th><th>When</th><th>Action</th><th>Who</th><th>Details</th><th>Hash</th></tr></thead>
              <tbody>{shown.map((e) => (
                <tr key={e.seq} data-testid="ledger-entry">
                  <td className="faint">{e.seq}</td>
                  <td className="small mono">{e.at.slice(0, 19).replace("T", " ")}</td>
                  <td className="mono small">{e.action}</td>
                  <td className="small">{e.actor}</td>
                  <td className="small muted" style={{ maxWidth: 420, wordBreak: "break-word" }}>{JSON.stringify(e.data).slice(0, 220)}</td>
                  <td className="hash">{e.hash.slice(0, 12)}</td>
                </tr>))}
              </tbody></table></div>
          </div>
        );
      }}
    </Query>
  );
}
