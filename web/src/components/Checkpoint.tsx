import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useUser } from "../hooks";

/**
 * A blocking card for a person's decision: what happens, why, who decides. The decision goes to
 * the ledger with the name of whoever is acting.
 */
export function Checkpoint({ title, role, children, actions, caseId }: {
  title: string;
  role: string;
  children: ReactNode;
  caseId: string;
  actions: { label: string; primary?: boolean; danger?: boolean; run: (note: string) => Promise<unknown> }[];
}) {
  const [user] = useUser();
  const [note, setNote] = useState("");
  const client = useQueryClient();
  const act = useMutation({
    mutationFn: (run: (note: string) => Promise<unknown>) => run(note),
    onSuccess: () => client.invalidateQueries({ queryKey: ["case", caseId] }),
  });
  return (
    <section className="card pending stack" aria-label={title} style={{ gap: 8 }}>
      <div className="row">
        <ShieldAlert size={16} /> <b>{title}</b>
        <span className="spacer" />
        <span className="badge s-pending">for the {role}</span>
      </div>
      <div className="small">{children}</div>
      <label className="field small">
        <span className="muted">Note for the ledger</span>
        <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <div className="row">
        {actions.map((a) => (
          <button key={a.label} className={`btn ${a.primary ? "primary" : ""} ${a.danger ? "danger" : ""}`}
                  disabled={!user || act.isPending} onClick={() => act.mutate(a.run)}>{a.label}</button>
        ))}
        <span className="faint">{user ? `Recorded as ${user}.` : "Say who you are first (top right)."}</span>
      </div>
      {act.isError && <div className="error-text small" role="alert">{(act.error as Error).message}</div>}
    </section>
  );
}
