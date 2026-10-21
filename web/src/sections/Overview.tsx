import { useQuery } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";
import { api } from "../api/client";
import type { ClaimsView } from "../api/types";
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
    <div className="stack" style={{ gap: 6 }}>
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

/** Order mirrors how a reader weighs them: strongest first. */
const BANDS: { key: string; cls: string; label: string }[] = [
  { key: "supported", cls: "ok", label: "supported" },
  { key: "partially_supported", cls: "weak", label: "too weak to settle" },
  { key: "contested", cls: "warn", label: "contested" },
  { key: "unverified", cls: "unknown", label: "unverified" },
  { key: "contradicted", cls: "bad", label: "contradicted" },
];

/** The case's shape in one glance: counts by status, and how the sub-claims divide. */
function StatStrip({ view }: { view: ClaimsView }) {
  const c = useCaseContext();
  const total = view.subclaims.length;
  if (!total) return null;
  const counts = new Map<string, number>();
  for (const s of view.subclaims) counts.set(s.status, (counts.get(s.status) ?? 0) + 1);
  const shown = BANDS.filter((b) => counts.get(b.key));
  const unchallenged = view.subclaims.filter((s) => !s.challenged && s.status === "supported").length;
  const noEvidence = view.subclaims.filter((s) => s.evidence.supports.length === 0 && s.evidence.contradicts.length === 0).length;
  const mostOrigins = view.subclaims.reduce(
    (n, s) => Math.max(n, s.independent_origins.for, s.independent_origins.against), 0);

  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="stat-strip">
        <div className="stat-tile">
          <span className="value accent">{total}</span>
          <span className="label">Sub-claims</span>
          <span className="sub">{view.hypotheses.length} hypotheses</span>
        </div>
        <div className="stat-tile">
          <span className="value">{c.counts?.evidence ?? 0}</span>
          <span className="label">Evidence items</span>
          <span className="sub">{c.counts?.pending_proposals ?? 0} awaiting review</span>
        </div>
        <div className="stat-tile">
          <span className="value">{c.counts?.documents ?? 0}</span>
          <span className="label">Documents</span>
          <span className="sub">up to {mostOrigins} independent origins</span>
        </div>
        <div className="stat-tile">
          <span className="value">{noEvidence}</span>
          <span className="label">No evidence yet</span>
          <span className="sub">unresolved sub-claims</span>
        </div>
        <div className="stat-tile">
          <span className="value">{unchallenged}</span>
          <span className="label">Never challenged</span>
          <span className="sub">supported but untested</span>
        </div>
      </div>
      <div className="stack" style={{ gap: 6 }}>
        <div className="distribution" role="img" aria-label={shown.map((b) => `${counts.get(b.key)} ${b.label}`).join(", ")}>
          {shown.map((b) => (
            <i key={b.key} className={b.cls} style={{ width: `${((counts.get(b.key) ?? 0) / total) * 100}%` }} />
          ))}
        </div>
        <div className="distribution-legend">
          {shown.map((b) => (
            <span className="key" key={b.key}>
              <span className={`swatch distribution ${b.cls}`} style={{ background: `var(--${b.cls === "weak" ? "warn" : b.cls})` }} />
              {counts.get(b.key)} {b.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

export function Overview() {
  const c = useCaseContext();
  const q = useCaseView(c.id, "analysis", api.analysis);
  const claims = useCaseView(c.id, "claims", api.claims);
  return (
    <div className="stack">
      <LegalCheckpoint />
      <Alerts caseId={c.id} />
      <Query q={claims}>
        {(data) => data && <StatStrip view={data} />}
      </Query>
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