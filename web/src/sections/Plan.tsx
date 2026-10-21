import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import type { PlannedTask, Task } from "../api/types";
import { Checkpoint } from "../components/Checkpoint";
import { Query } from "../components/Query";
import { StatusBadge } from "../components/status";
import { useCaseView, useUser } from "../hooks";
import { useCaseContext } from "./CaseLayout";

export const SPECIALISTS: Record<string, string> = {
  official: "Official publications (JORT, TUNEPS, ministries)",
  funders_audit: "Lenders, audits, statistics",
  web_news: "Press",
  social: "Public social media",
  telegram: "Public Telegram channels",
};

const PURPOSE: Record<string, string> = {
  support: "find evidence",
  challenge: "look for what would refute it or explain it innocently",
  explore: "explore",
};

const toPlanned = (t: Task): PlannedTask => ({
  specialist: t.specialist, objective: t.objective, subclaim_ids: t.subclaim_ids, purpose: t.purpose,
  queries: t.queries, urls: t.urls, expectation_id: t.expectation_id,
});

function TaskEditor({ t, onChange, onRemove }: { t: PlannedTask; onChange: (t: PlannedTask) => void; onRemove: () => void }) {
  const list = (v: string) => v.split(",").map((x) => x.trim()).filter(Boolean);
  return (
    <div className="card stack" style={{ gap: 6 }} data-testid="task-editor">
      <div className="row">
        <select className="input" style={{ width: "auto" }} value={t.specialist} aria-label="Specialist"
                onChange={(e) => onChange({ ...t, specialist: e.target.value })}>
          {Object.keys(SPECIALISTS).map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="input" style={{ width: "auto" }} value={t.purpose} aria-label="Purpose"
                onChange={(e) => onChange({ ...t, purpose: e.target.value as PlannedTask["purpose"] })}>
          {Object.keys(PURPOSE).map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <span className="spacer" />
        <button className="btn ghost danger" onClick={onRemove} aria-label="Remove task"><Trash size={14} /></button>
      </div>
      <textarea className="input" rows={2} value={t.objective} aria-label="Objective"
                onChange={(e) => onChange({ ...t, objective: e.target.value })} />
      <div className="row small">
        <label className="field" style={{ flex: 1 }}>Sub-claims
          <input className="input" value={t.subclaim_ids.join(", ")} onChange={(e) => onChange({ ...t, subclaim_ids: list(e.target.value) })} />
        </label>
        <label className="field" style={{ flex: 2 }}>Queries
          <input className="input" value={t.queries.join(", ")} onChange={(e) => onChange({ ...t, queries: list(e.target.value) })} />
        </label>
      </div>
    </div>
  );
}

function TaskRow({ t }: { t: Task }) {
  return (
    <div className="card stack" style={{ gap: 4 }}>
      <div className="row small">
        <span className="mono">{t.id}</span>
        <span className="badge s-neutral">{t.purpose}</span>
        {t.round > 1 && <span className="faint">round {t.round}</span>}
        {t.expectation_id && <span className="faint">searches for <span className="mono">{t.expectation_id}</span></span>}
        {t.suspicion_id && <span className="faint">tests <span className="mono">{t.suspicion_id}</span></span>}
        <span className="faint">by {t.created_by}</span>
        <span className="spacer" />
        {t.status === "done" ? <StatusBadge status={t.outcome ?? "found"} /> : <span className="badge s-unknown">open</span>}
      </div>
      <div>{t.objective}</div>
      <div className="faint">
        {t.subclaim_ids.length > 0 && <>Sub-claims <span className="mono">{t.subclaim_ids.join(", ")}</span>. </>}
        {t.queries.length > 0 && <>Queries: {t.queries.map((q) => `« ${q} »`).join(", ")}</>}
      </div>
      {t.note && <div className="small muted">Outcome: {t.note}</div>}
    </div>
  );
}

export function Plan() {
  const c = useCaseContext();
  const q = useCaseView(c.id, "plan", api.plan);
  const [draft, setDraft] = useState<PlannedTask[] | null>(null);
  const [user] = useUser();
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (tasks: PlannedTask[]) => api.editPlan(c.id, tasks),
    onSuccess: (plan) => {
      client.setQueryData(["case", c.id, "plan"], plan);
      setDraft(null);
    },
  });
  return (
    <Query q={q}>
      {(plan) => {
        if (!plan.tasks) return <div className="empty">No plan yet ({c.status.replaceAll("_", " ")}).</div>;
        const bySpecialist = Object.keys(SPECIALISTS).filter((s) => plan.tasks!.some((t) => t.specialist === s));
        return (
          <div className="stack">
            {plan.editable && !draft && (
              <Checkpoint caseId={c.id} title="Approve the plan" role="investigator" actions={[
                { label: "Approve and start", primary: true, run: () => api.approvePlan(c.id) },
              ]}>
                The specialists will work these tasks in parallel, then the reviewer checks what they propose.
                You can edit the plan first: code will put back anything the engine requires and say why.
              </Checkpoint>
            )}
            {plan.fixes && plan.fixes.length > 0 && (
              <details className="card small" aria-label="What code put back">
                <summary><b>What code added or changed in the plan</b> <span className="faint">({plan.fixes.length}):
                  the engine requires two kinds of source per core sub-claim, a search per expected record and a test per
                  innocent explanation</span></summary>
                <div className="stack" style={{ gap: 2, marginTop: 6 }}>{plan.fixes.map((f, i) => <div key={i}>{f}</div>)}</div>
              </details>
            )}
            <div className="row small">
              <span className="muted">Budgets (tool calls):</span>
              {Object.entries(plan.budgets ?? {}).map(([s, n]) => <span key={s} className="badge s-neutral">{s} {n}</span>)}
              <span className="spacer" />
              {plan.editable && !draft && (
                <button className="btn" onClick={() => setDraft(plan.tasks!.map(toPlanned))}><Pencil size={14} /> Edit tasks</button>
              )}
            </div>
            {draft ? (
              <div className="stack">
                {draft.map((t, i) => (
                  <TaskEditor key={i} t={t} onChange={(n) => setDraft(draft.map((x, j) => (j === i ? n : x)))}
                              onRemove={() => setDraft(draft.filter((_, j) => j !== i))} />
                ))}
                <div className="row">
                  <button className="btn" onClick={() => setDraft([...draft, {
                    specialist: "official", objective: "", subclaim_ids: [], purpose: "support", queries: [], urls: [],
                  }])}><Plus size={14} /> Add a task</button>
                  <span className="spacer" />
                  <button className="btn" onClick={() => setDraft(null)}>Cancel</button>
                  <button className="btn primary" disabled={!user || save.isPending || draft.some((t) => !t.objective.trim())}
                          onClick={() => save.mutate(draft)}>Save the plan</button>
                </div>
                {save.isError && <div className="error-text" role="alert">{(save.error as Error).message}</div>}
              </div>
            ) : bySpecialist.map((s) => (
              <section key={s} className="stack" style={{ gap: 6 }}>
                <h3 className="section-title">{s} <span className="faint">{SPECIALISTS[s]}</span></h3>
                {plan.tasks!.filter((t) => t.specialist === s).map((t) => <TaskRow key={t.id} t={t} />)}
              </section>
            ))}
          </div>
        );
      }}
    </Query>
  );
}
