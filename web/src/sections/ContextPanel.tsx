import { useQuery } from "@tanstack/react-query";
import { GitCompareArrows, X } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import type { DocumentFull, EvidenceItem } from "../api/types";
import { Query } from "../components/Query";
import { formatTnd, SourceIcon, SourceLine } from "../components/sources";
import { StatusBadge } from "../components/status";
import { usePanel } from "../panel";
import { highlight } from "../text";

const INTEREST: Record<string, string> = {
  self_serving: "Party speaking in its own favour: weighs half until confirmed independently",
  against_interest: "A party conceding a point against its own interest: strong evidence",
};

function EvidenceDetail({ caseId, id }: { caseId: string; id: string }) {
  const q = useQuery({ queryKey: ["case", caseId, "evidence"], queryFn: () => api.evidence(caseId) });
  return (
    <Query q={q}>
      {({ items }) => {
        const e = items.find((i) => i.evidence_id === id);
        if (!e) return <div className="muted">{id} does not count in this case (never accepted, or disputed since).</div>;
        return (
          <div className="stack">
            <EvidenceSummary e={e} />
            {e.source && <DocumentViewer caseId={caseId} docId={e.source.doc_id} focus={id} />}
          </div>
        );
      }}
    </Query>
  );
}

export function EvidenceSummary({ e }: { e: EvidenceItem }) {
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row">
        <SourceIcon kind={e.type === "quote" ? e.source!.kind : e.type} />
        <b>{e.type === "quote" ? "Quote" : e.type === "amount" ? "Amount" : "Absence"}</b>
        {e.subclaim_id && <span className="small">{e.relation} <span className="mono">{e.subclaim_id}</span></span>}
        <span className="spacer" />
        <StatusBadge status={e.status} />
      </div>
      {e.type === "quote" && <blockquote className="quote">« {e.quote} »</blockquote>}
      {e.type === "amount" && (
        <div>
          <b>{formatTnd(e.amount_tnd!)}</b> <span className="muted">({e.role})</span>
          <blockquote className="quote">« {e.quote} »</blockquote>
          <div className="faint">{e.used_by_financial_check ? "Used by the financial check."
            : "Not used by the financial check (a version that diverges from an earlier attested copy)."}</div>
        </div>
      )}
      {e.type === "absence" && (
        <div className="stack" style={{ gap: 4 }}>
          <div>Nothing found in <b>{e.register_name}</b></div>
          <div className="small">Query: <span className="mono">{e.query}</span></div>
          <div className="faint">Searched {e.searched_at?.slice(0, 10)} ·
            {e.capture ? <> capture <span className="mono">{e.capture}</span></> : " no capture of the empty result stored: counts half"}</div>
        </div>
      )}
      {e.source && <SourceLine kind={e.source.kind} publisher={e.source.publisher} reliability={e.source.reliability}
                               date={e.source.published_at ?? e.source.observed_at} />}
      <div className="row small muted">
        {e.weight != null && <span>weight {e.weight.toFixed(2)} (computed)</span>}
        {e.origin && <span>· origin <span className="mono">{e.origin}</span></span>}
      </div>
      {e.publisher_interest && e.publisher_interest !== "none" && (
        <div className="alert info small">{INTEREST[e.publisher_interest]}</div>
      )}
      {(e.proposed_by || e.review_note) && (
        <div className="faint">{e.proposed_by && <>Proposed by {e.proposed_by}. </>}{e.review_note && <>Reviewer: {e.review_note}</>}</div>
      )}
    </div>
  );
}

function Versions({ caseId, docId }: { caseId: string; docId: string }) {
  const q = useQuery({ queryKey: ["case", caseId, "versions", docId], queryFn: () => api.versions(caseId, docId) });
  return (
    <Query q={q}>
      {(v) => v.versions.length < 2 ? <div className="faint">Only one version stored.</div> : (
        <div className="stack">
          {v.changes.map((c) => (
            <div key={c.from + c.to} className={`alert ${c.changes.length ? "warn" : "info"} small`}>
              <span><span className="mono">{c.from}</span> → <span className="mono">{c.to}</span>:{" "}
                {c.changes.length ? c.changes.map((x) => `${x.kind} ${x.removed.join(", ")} → ${x.added.join(", ")}`).join("; ")
                  : "no field changed"}</span>
            </div>
          ))}
          <div style={{ display: "grid", gridTemplateColumns: `repeat(${v.versions.length}, minmax(0, 1fr))`, gap: 8 }}>
            {v.versions.map((x) => (
              <div key={x.doc_id} className="stack" style={{ gap: 4 }}>
                <span className="mono small">{x.doc_id}</span>
                <span className="faint">{x.kind.replaceAll("_", " ")} · seen {x.observed_at.slice(0, 10)}</span>
                <div className="doc-text" dir="auto">{x.text}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Query>
  );
}

function Custody({ d }: { d: DocumentFull }) {
  const c = d.custody;
  return (
    <div className="stack small" style={{ gap: 4 }}>
      <b>Chain of custody</b>
      <div>Stored bytes {c.bytes_intact ? "match their recorded hash" : <span className="error-text">no longer match their hash</span>}</div>
      <div>Raw SHA-256 <div className="hash">{c.raw_sha256}</div></div>
      <div>Text SHA-256 <div className="hash">{c.text_sha256}</div></div>
      <div>Extraction: {c.extraction}{c.extraction === "ocr" && " (OCR: check figures against the scan)"}</div>
      <div className="faint">URL: <a href={d.url} target="_blank" rel="noreferrer noopener">{d.url}</a></div>
      {d.canonical_url !== d.url && <div className="faint">Same document as {d.canonical_url}</div>}
      {c.captured.map((e) => <div key={e.seq} className="faint">Captured by {e.actor} at {e.at.slice(0, 16)} (ledger #{e.seq})</div>)}
      {(c.cites.length > 0 || c.derived_from.length > 0) && (
        <div className="faint">Cites {c.cites.join(", ") || "nothing"}; derived from {c.derived_from.join(", ") || "nothing"}</div>
      )}
    </div>
  );
}

export function DocumentViewer({ caseId, docId, focus }: { caseId: string; docId: string; focus?: string }) {
  const q = useQuery({ queryKey: ["case", caseId, "document", docId], queryFn: () => api.document(caseId, docId) });
  const [compare, setCompare] = useState(false);
  return (
    <Query q={q}>
      {(d) => {
        const parts = highlight(d.text, d.highlights.map((h) => ({ id: h.evidence_id, quote: h.quote })));
        return (
          <div className="stack">
            <div className="stack" style={{ gap: 2 }}>
              <SourceLine kind={d.kind} publisher={d.publisher} reliability={d.reliability} date={d.published_at ?? d.observed_at} />
              {d.title && <b>{d.title}</b>}
              <span className="mono faint">{d.doc_id}</span>
            </div>
            <div className="doc-text" dir="auto" data-testid="document-text">
              {parts.map((p, i) => p.id ? (
                <mark key={i} title={p.id} data-evidence={p.id} style={p.id === focus ? { fontWeight: 600 } : undefined}>{p.text}</mark>
              ) : <span key={i}>{p.text}</span>)}
            </div>
            {d.used_by.length > 0 && <div className="small">Evidence from this document: <span className="mono">{d.used_by.join(", ")}</span></div>}
            <Custody d={d} />
            <button className="btn" onClick={() => setCompare(!compare)}><GitCompareArrows size={14} /> {compare ? "Hide" : "Compare"} versions</button>
            {compare && <Versions caseId={caseId} docId={docId} />}
          </div>
        );
      }}
    </Query>
  );
}

export function ContextPanel({ caseId, selected }: { caseId: string; selected: string }) {
  const { close } = usePanel();
  const isDoc = selected.startsWith("doc:");
  return (
    <aside className="context" aria-label="Context">
      <div className="context-head">
        <b className="mono">{isDoc ? selected.slice(4) : selected}</b>
        <span className="spacer" />
        <button className="btn ghost" aria-label="Close" onClick={close}><X size={15} /></button>
      </div>
      <div className="context-body">
        {isDoc ? <DocumentViewer caseId={caseId} docId={selected.slice(4)} /> : <EvidenceDetail caseId={caseId} id={selected} />}
      </div>
    </aside>
  );
}
