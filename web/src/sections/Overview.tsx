import { useQuery } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";
import { api } from "../api/client";
import { Markdown } from "../components/Markdown";
import { Query } from "../components/Query";
import { useCaseView } from "../hooks";
import { usePanel } from "../panel";
import { useCaseContext } from "./CaseLayout";
import { LegalCheckpoint } from "./LegalCheckpoint";

/** Alerts from computed facts: rewritten records, contested claims, single origins. */
function Alerts({ caseId }: { caseId: string }) {
  const timeline = useQuery({ queryKey: ["case", caseId, "timeline"], queryFn: () => api.timeline(caseId) });
  const claims = useQuery({ queryKey: ["case", caseId, "claims"], queryFn: () => api.claims(caseId) });
  const { openDocument } = usePanel();
  const rewrites = timeline.data?.events.filter((e) => e.type === "rewrite") ?? [];
  const contested = claims.data?.subclaims.filter((c) => c.status === "contested") ?? [];
  const decisive = claims.data?.depends_on?.filter((d) => d.changes_verdict) ?? [];
  if (!rewrites.length && !contested.length && !decisive.length) return null;
  return (
    <div className="stack" style={{ gap: 6, marginBottom: 12 }}>
      {rewrites.map((r) => (
        <div key={r.doc_id} className="alert warn">
          <TriangleAlert size={16} />
          <span><b>Record rewritten</b>: <span className="mono">{r.earlier_doc_id}</span> →{" "}
            <button className="chip" onClick={() => openDocument(r.doc_id!)}>{r.doc_id}</button> {r.text}
            {r.needs_review && " (OCR text: verify against the scan)"}</span>
        </div>
      ))}
      {contested.map((c) => (
        <div key={c.id} className="alert warn"><TriangleAlert size={16} />
          <span><b>Contested</b>: <span className="mono">{c.id}</span> {c.statement}</span></div>
      ))}
      {decisive.map((d) => (
        <div key={d.origin.join()} className="alert info"><TriangleAlert size={16} />
          <span><b>Single origin</b>: without <span className="mono">{d.origin.join(", ")}</span>,{" "}
            {d.changes.join("; ").replaceAll(" -> ", " → ").replaceAll("_", " ")}</span></div>
      ))}
    </div>
  );
}

export function Overview() {
  const c = useCaseContext();
  const q = useCaseView(c.id, "analysis", api.analysis);
  return (
    <div className="stack">
      <LegalCheckpoint />
      <Alerts caseId={c.id} />
      <Query q={q}>
        {({ sections }) => sections.length === 0 ? (
          <div className="empty">{c.status === "refused" ? `Refused by the legal policy: ${c.note}`
            : c.status === "failed" ? `The case failed: ${c.note}` : "No assessment yet: the investigation has not started."}</div>
        ) : (
          <div className="stack">
            {sections.map((s, i) => (
              <section key={s.title} className={i === 0 ? "card" : ""}>
                <h2 className="section-title">{s.title}</h2>
                <Markdown text={s.markdown} />
              </section>
            ))}
          </div>
        )}
      </Query>
    </div>
  );
}
