import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import type { ClaimsView, SubclaimCard } from "../api/types";
import { Chips } from "../components/Chip";
import { Query } from "../components/Query";
import { ConfidenceMeter, percent, StatusBadge } from "../components/status";
import { useCaseView } from "../hooks";
import { useCaseContext } from "./CaseLayout";

const BEARING: Record<string, string> = {
  against: "against the accused",
  for: "for the accused: tests an innocent explanation",
  neutral: "context",
};

/** "How this was concluded": written from computed values only. */
function Reasoning({ s, view }: { s: SubclaimCard; view: ClaimsView }) {
  const decides = (view.depends_on ?? []).filter((d) => d.changes.some((c) => c.startsWith(`${s.id} `)));
  return (
    <div className="small stack" style={{ gap: 4 }}>
      <div>Support {s.support.toFixed(2)} from {s.independent_origins.for} independent origin(s); contradiction{" "}
        {s.contradiction.toFixed(2)} from {s.independent_origins.against}. Documents sharing an origin count once.</div>
      <div>Likelihood that it is true: {s.likelihood_term}{s.likelihood != null && ` (${percent(s.likelihood)})`}, computed.</div>
      {decides.map((d) => (
        <div key={d.origin.join()}>Without <span className="mono">{d.origin.join(", ")}</span>:{" "}
          {d.changes.filter((c) => c.startsWith(`${s.id} `)).join("; ").replaceAll(" -> ", " → ")}</div>
      ))}
      {!s.challenged && s.status === "supported" && <div>Nobody has yet looked for evidence against it.</div>}
    </div>
  );
}

export function ClaimCard({ s, view }: { s: SubclaimCard; view: ClaimsView }) {
  const [open, setOpen] = useState(false);
  return (
    <article className="card stack" style={{ gap: 8 }} data-testid={`claim-${s.id}`}>
      <div className="row">
        <span className="mono">{s.id}</span>
        {s.core && <span className="badge s-neutral">core</span>}
        <StatusBadge status={s.status} />
        <span className="spacer" />
        <span className="faint">{BEARING[s.bearing]}</span>
      </div>
      <div style={{ fontWeight: 500 }}>{s.statement}</div>
      <div className="row small">
        <span>{s.likelihood_term} true</span>
        <ConfidenceMeter level={s.confidence} />
        {!s.challenged && s.status === "supported" && <span className="badge s-unknown">never challenged</span>}
      </div>
      {s.confidence !== "high" && s.confidence_reasons.length > 0 && (
        <div className="faint">Confidence capped by: {s.confidence_reasons.join("; ").replaceAll(" -> ", " → ")}</div>
      )}
      <div className="grid-3">
        <div><div className="faint">For · {s.independent_origins.for} origin(s)</div><Chips ids={s.evidence.supports} /></div>
        <div><div className="faint">Against · {s.independent_origins.against} origin(s)</div><Chips ids={s.evidence.contradicts} /></div>
        <div><div className="faint">Qualifying</div><Chips ids={s.evidence.qualifies} /></div>
      </div>
      {s.expected_records.length > 0 && (
        <div className="small">
          <div className="faint">Expected records</div>
          {s.expected_records.map((r, i) => (
            <div key={i}>{r.description} <span className="faint">({r.register_id}; if absent it {r.absence_means === "supports" ? "supports" : "contradicts"} {s.id})</span></div>
          ))}
        </div>
      )}
      <button className="btn ghost small" style={{ alignSelf: "flex-start", padding: "2px 4px" }} onClick={() => setOpen(!open)}
              aria-expanded={open}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />} How this was concluded
      </button>
      {open && <Reasoning s={s} view={view} />}
    </article>
  );
}

const ORDER = ["supported", "contested", "partially_supported", "unverified", "contradicted"];

export function Claims() {
  const c = useCaseContext();
  const q = useCaseView(c.id, "claims", api.claims);
  const [coreOnly, setCoreOnly] = useState(false);
  const [bearing, setBearing] = useState("all");
  const [unchallenged, setUnchallenged] = useState(false);
  const [layout, setLayout] = useState<"cards" | "board">("cards");
  return (
    <Query q={q}>
      {(view) => {
        const shown = view.subclaims.filter((s) => (!coreOnly || s.core) && (bearing === "all" || s.bearing === bearing)
          && (!unchallenged || (!s.challenged && s.status === "supported")));
        return (
          <div className="stack">
            <div className="row small">
              <label className="row"><input type="checkbox" checked={coreOnly} onChange={(e) => setCoreOnly(e.target.checked)} /> core only</label>
              <label className="row">bearing
                <select className="input" style={{ width: "auto" }} value={bearing} onChange={(e) => setBearing(e.target.value)}>
                  <option value="all">all</option><option value="against">against the accused</option>
                  <option value="for">innocent explanations</option><option value="neutral">context</option>
                </select></label>
              <label className="row"><input type="checkbox" checked={unchallenged} onChange={(e) => setUnchallenged(e.target.checked)} /> never challenged</label>
              <span className="spacer" />
              <button className={`btn ${layout === "cards" ? "primary" : ""}`} onClick={() => setLayout("cards")}>Cards</button>
              <button className={`btn ${layout === "board" ? "primary" : ""}`} onClick={() => setLayout("board")}>Board</button>
            </div>
            {layout === "cards" ? shown.map((s) => <ClaimCard key={s.id} s={s} view={view} />) : (
              <div style={{ display: "grid", gridTemplateColumns: `repeat(${ORDER.length}, minmax(180px, 1fr))`, gap: 8, overflowX: "auto" }}>
                {ORDER.map((status) => (
                  <div key={status} className="stack" style={{ gap: 6 }}>
                    <StatusBadge status={status} />
                    {shown.filter((s) => s.status === status).map((s) => (
                      <div key={s.id} className="card small"><span className="mono">{s.id}</span> {s.statement}
                        <div className="faint">{s.likelihood_term} · {s.confidence} confidence</div></div>
                    ))}
                  </div>
                ))}
              </div>
            )}
            {shown.length === 0 && <div className="faint">No sub-claim matches these filters.</div>}
          </div>
        );
      }}
    </Query>
  );
}
