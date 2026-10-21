import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleDot, Pause, Play, Square } from "lucide-react";
import { api } from "../api/client";
import type { CaseOverview } from "../api/types";
import { ago } from "../components/Query";
import { CaseStatusBadge, ConfidenceMeter, VerdictBadge } from "../components/status";
import { useUser } from "../hooks";

export const STOPS: Record<string, string> = {
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

/** The judgment, given the room it deserves: size and space, never a status hue. */
function Assessment({ c }: { c: CaseOverview }) {
  const a = c.assessment;
  if (!a) {
    return (
      <div className="verdict-panel">
        <span className="none">
          No assessment yet{["preparing", "awaiting_plan_approval", "running", "paused"].includes(c.status)
            ? ": the investigation has not finished gathering evidence."
            : "."}
        </span>
      </div>
    );
  }
  return (
    <div className="verdict-panel" data-testid="assessment">
      <span className="stack" style={{ gap: 2 }}>
        <span className="label">Verdict</span>
        <VerdictBadge verdict={a.verdict} />
      </span>
      <span className="stack" style={{ gap: 2 }}>
        <span className="label">Core facts</span>
        <span className="verdict-word">{a.likelihood_term}</span>
      </span>
      <span className="stack" style={{ gap: 2 }}>
        <span className="label">Confidence</span>
        <ConfidenceMeter level={a.confidence} />
      </span>
      <span className="stack" style={{ gap: 2 }}>
        <span className="label">Basis</span>
        <span className="small">{a.final ? "final" : "so far"}</span>
      </span>
      {c.stop_reason && (
        <span className="stack" style={{ gap: 2 }}>
          <span className="label">Stopped</span>
          <span className="small">{STOPS[c.stop_reason] ?? c.stop_reason}</span>
        </span>
      )}
    </div>
  );
}

export function CaseHeader({ c }: { c: CaseOverview }) {
  const live = c.status === "running" || c.status === "paused";
  return (
    <div className="case-header">
      <div className="row">
        <span className="mono muted">{c.id}</span>
        {live && <CircleDot size={13} aria-hidden style={{ color: c.status === "running" ? "var(--accent)" : "var(--text-3)" }} />}
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
      <Assessment c={c} />
      <div className="meta-rail">
        {c.parties.length > 0 && (
          <span className="kv"><span className="k">parties</span>
            <span>{c.parties.map((p) => `${p.name} (${p.role})`).join("; ")}</span></span>
        )}
        {c.rounds > 0 && <span className="kv"><span className="k">rounds</span>{c.rounds}</span>}
        {c.counts && c.counts.tool_calls > 0 && (
          <span className="kv"><span className="k">tool calls</span>{c.counts.tool_calls}</span>
        )}
        {c.counts && c.counts.evidence > 0 && (
          <span className="kv"><span className="k">evidence</span>{c.counts.evidence}</span>
        )}
        {c.counts && c.counts.documents > 0 && (
          <span className="kv"><span className="k">documents</span>{c.counts.documents}</span>
        )}
        {c.counts && c.counts.open_suspicions > 0 && (
          <span className="kv"><span className="k">open suspicions</span>{c.counts.open_suspicions}</span>
        )}
        <span className="kv"><span className="k">opened by</span>{c.created_by}</span>
        <span className="kv"><span className="k">last activity</span>{ago(c.last_activity)}</span>
      </div>
      {c.note && c.status !== "in_review" && <div className="faint" style={{ marginTop: 6 }}>{c.note}</div>}
    </div>
  );
}