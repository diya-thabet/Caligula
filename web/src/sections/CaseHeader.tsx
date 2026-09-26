import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, Square } from "lucide-react";
import { api } from "../api/client";
import type { CaseOverview } from "../api/types";
import { ago } from "../components/Query";
import { CaseStatusBadge, ConfidenceMeter, VerdictBadge } from "../components/status";
import { useUser } from "../hooks";

const STOPS: Record<string, string> = {
  settled: "settled: confidence is high and no suspicion is open",
  exhausted: "exhausted: the last round brought nothing new",
  no_open_tasks: "nothing left to do",
  budget: "the tool-call budget is spent",
  round_limit: "the round limit was reached",
  stopped: "stopped by the investigator",
};

function RunControls({ c }: { c: CaseOverview }) {
  const [user] = useUser();
  const client = useQueryClient();
  const act = useMutation({
    mutationFn: (what: "pause" | "resume" | "stop") => api[what](c.id),
    onSuccess: (data) => client.setQueryData(["case", c.id, "overview"], data),
  });
  if (c.status !== "running" && c.status !== "paused") return null;
  const title = user ? undefined : "Say who you are first (top right)";
  return (
    <span className="row">
      {c.status === "running" ? (
        <button className="btn" disabled={!user || act.isPending} title={title} onClick={() => act.mutate("pause")}>
          <Pause size={14} /> Pause
        </button>
      ) : (
        <button className="btn" disabled={!user || act.isPending} title={title} onClick={() => act.mutate("resume")}>
          <Play size={14} /> Resume
        </button>
      )}
      <button className="btn danger" disabled={!user || act.isPending} title={title}
              onClick={() => window.confirm("Stop the investigation? What was recorded still counts.") && act.mutate("stop")}>
        <Square size={14} /> Stop
      </button>
      {act.isError && <span className="error-text small">{(act.error as Error).message}</span>}
    </span>
  );
}

export function CaseHeader({ c }: { c: CaseOverview }) {
  const a = c.assessment;
  return (
    <div className="case-header">
      <div className="row">
        <span className="mono muted">{c.id}</span>
        <CaseStatusBadge status={c.status} />
        <span className="faint">{c.mode === "factcheck" ? "fact-check" : "investigation"}
          {c.claim_type ? ` · ${c.claim_type.replaceAll("_", " ")}` : ""}</span>
        <span className="spacer" />
        {c.sign_off ? (
          <span className="small">Approved by <b>{c.sign_off.by}</b>, {c.sign_off.at.slice(0, 16).replace("T", " ")}</span>
        ) : <span className="badge s-neutral">Draft</span>}
        <RunControls c={c} />
      </div>
      <div className="claim">{c.claim}</div>
      <div className="row small" style={{ gap: 14 }}>
        {a ? (
          <span className="row" data-testid="assessment">
            <VerdictBadge verdict={a.verdict} />
            <span>core facts <b>{a.likelihood_term}</b></span>
            <ConfidenceMeter level={a.confidence} />
            <span className="faint">{a.final ? "final" : "so far"}</span>
          </span>
        ) : <span className="faint">No assessment yet</span>}
        {c.parties.length > 0 && (
          <span className="kv"><span className="k">parties</span>
            {c.parties.map((p) => `${p.name} (${p.role})`).join("; ")}</span>)}
        {c.rounds > 0 && <span className="kv"><span className="k">rounds</span>{c.rounds}</span>}
        {c.counts && <span className="kv"><span className="k">tool calls</span>{c.counts.tool_calls}</span>}
        <span className="kv"><span className="k">opened by</span>{c.created_by}</span>
        <span className="kv"><span className="k">last activity</span>{ago(c.last_activity)}</span>
        {c.stop_reason && <span className="kv"><span className="k">stopped</span>{STOPS[c.stop_reason] ?? c.stop_reason}</span>}
      </div>
      {c.note && c.status !== "in_review" && <div className="faint" style={{ marginTop: 4 }}>{c.note}</div>}
    </div>
  );
}
