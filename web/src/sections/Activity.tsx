import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import type { CaseEvent } from "../api/types";
import { Query } from "../components/Query";
import { STOPS } from "./CaseHeader";
import { useCaseContext } from "./CaseLayout";

/** A phase's detail in words; a round's summary comes as JSON from the team. */
function phaseDetail(phase: string, detail: string): string {
  if (phase !== "round") return detail;
  try {
    const r = JSON.parse(detail);
    const closed = Object.keys(r.tasks_closed ?? {}).length;
    const raised = (r.suspicions_raised ?? []).length;
    return `round ${r.round} closed: ${closed} task(s) done, ${r.new_accepted} new evidence item(s)`
      + (raised ? `, ${raised} suspicion(s) raised` : "")
      + `; ${String(r.verdict).replaceAll("_", " ")}, ${r.confidence} confidence`;
  } catch {
    return detail;
  }
}

const LIVE = new Set(["preparing", "running", "paused"]);

function describe(args: Record<string, any>): string {
  const keys = ["query", "doc_id", "subclaim_id", "task_id", "url", "canonical_url", "quote", "proposal_id", "outcome", "statement"];
  return keys.filter((k) => args[k] != null && args[k] !== "").map((k) => {
    const v = String(args[k]);
    return k === "quote" || k === "query" || k === "statement" ? `« ${v.slice(0, 90)}${v.length > 90 ? "…" : ""} »` : v;
  }).join(" · ");
}

/** A tool call as the engine saw it. Refusals by code are the engine working, not failures. */
function ToolCall({ e }: { e: CaseEvent }) {
  const refused = String(e.data.outcome ?? "").startsWith("error:");
  return (
    <div className="row small" style={{ alignItems: "baseline", gap: 8 }} data-testid="tool-call">
      <span className="faint mono">#{e.data.step}</span>
      <span className="mono">{e.data.tool}</span>
      <span className="muted" style={{ flex: 1, minWidth: 200 }}>{describe(e.data.args ?? {})}</span>
      <span className={refused ? "faint" : "small"} style={{ maxWidth: 380 }}>
        {refused ? <>refused by code: {String(e.data.outcome).slice(7, 200)}</> : String(e.data.outcome ?? "").slice(0, 160)}
      </span>
    </div>
  );
}

export function Activity() {
  const c = useCaseContext();
  const q = useQuery({
    queryKey: ["case", c.id, "events"],
    queryFn: () => api.events(c.id),
    refetchInterval: LIVE.has(c.status) ? 2000 : false,
  });
  const [ledger, setLedger] = useState(false);
  return (
    <Query q={q}>
      {(events) => {
        const tools = events.filter((e) => e.kind === "tool");
        const rounds = [...new Set(tools.map((e) => e.data.round as number))].sort((a, b) => a - b);
        const others = events.filter((e) => e.kind !== "tool" && (ledger || e.kind !== "audit"));
        return (
          <div className="stack">
            <div className="row small">
              <span className="muted">{tools.length} tool call(s)</span>
              {LIVE.has(c.status) && <span className="badge s-pending">{c.status === "paused" ? "paused" : "live"}</span>}
              <span className="spacer" />
              <label className="row"><input type="checkbox" checked={ledger} onChange={(e) => setLedger(e.target.checked)} /> show ledger entries</label>
            </div>
            <section className="card stack" style={{ gap: 4 }} aria-label="Progress">
              <b>Progress</b>
              {others.length === 0 && <span className="faint">Nothing yet.</span>}
              {others.map((e) => (
                <div key={e.seq} className="row small" style={{ gap: 8 }}>
                  <span className="faint mono">{e.at.slice(11, 19)}</span>
                  {e.kind === "status" && <span><b>{String(e.data.status).replaceAll("_", " ")}</b>
                    {e.data.note && <span className="muted"> — {STOPS[e.data.note] ?? e.data.note}</span>}</span>}
                  {e.kind === "phase" && <span><span className="badge s-neutral">{e.data.phase}</span>{" "}
                    <span className="muted">{phaseDetail(e.data.phase, String(e.data.detail)).slice(0, 240)}</span></span>}
                  {e.kind === "error" && <span className="error-text">{e.data.error}</span>}
                  {e.kind === "audit" && <span className="muted"><span className="mono">{e.data.action}</span> by {e.data.actor}</span>}
                </div>
              ))}
            </section>
            {rounds.map((r) => {
              const inRound = tools.filter((e) => e.data.round === r);
              const agents = [...new Set(inRound.map((e) => e.data.agent as string))];
              return (
                <section key={r} className="stack" style={{ gap: 6 }} aria-label={`Round ${r}`}>
                  <h3 className="section-title">Round {r}</h3>
                  {agents.map((a) => (
                    <details key={a} className="card" open={LIVE.has(c.status)}>
                      <summary className="row"><b>{a}</b><span className="faint">{inRound.filter((e) => e.data.agent === a).length} call(s)</span></summary>
                      <div className="stack" style={{ gap: 4, marginTop: 6 }}>
                        {inRound.filter((e) => e.data.agent === a).map((e) => <ToolCall key={e.seq} e={e} />)}
                      </div>
                    </details>
                  ))}
                </section>
              );
            })}
            {tools.length === 0 && <div className="faint">No agent has worked on this case in this server
              {c.status === "in_review" ? " (it was imported for review)" : ""}.</div>}
          </div>
        );
      }}
    </Query>
  );
}
