// Status badges, the verdict, confidence: semantic colours for status only (docs/ui.md §2).
import type { Confidence } from "../api/types";

type Tone = "ok" | "bad" | "warn" | "weak" | "unknown" | "pending" | "neutral";

const TONES: Record<string, Tone> = {
  // sub-claims
  supported: "ok", contradicted: "bad", contested: "warn", partially_supported: "weak", unverified: "unknown",
  // hypotheses
  consistent: "ok", falsified: "bad", open: "unknown",
  // suspicions
  confirmed: "ok", refuted: "bad", awaiting_scope: "pending", rejected: "neutral",
  // proposals
  accepted: "ok", disputed: "bad", pending: "pending",
  // summary sentences
  partial: "warn", unsupported: "bad", uncited: "bad", unjudged: "unknown", analysis: "neutral",
  // task outcomes
  found: "ok", not_found: "neutral", blocked: "warn",
};

const LABELS: Record<string, string> = {
  partially_supported: "too weak to settle",
  awaiting_scope: "awaiting lawyer",
  not_found: "not found",
  uncited: "removed: uncited",
  unsupported: "not in its evidence",
  unjudged: "checked in code",
  partial: "partly supported",
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const tone = TONES[status] ?? "neutral";
  return <span className={`badge s-${tone}`} data-status={status}>{label ?? LABELS[status] ?? status.replaceAll("_", " ")}</span>;
}

const CASE_LABELS: Record<string, string> = {
  refused: "Refused",
  awaiting_legal_review: "Awaiting legal review",
  preparing: "Preparing",
  awaiting_plan_approval: "Plan awaiting approval",
  running: "Running",
  paused: "Paused",
  in_review: "In review",
  approved: "Approved",
  failed: "Failed",
};

export function CaseStatusBadge({ status }: { status: string }) {
  const waiting = status.startsWith("awaiting") || status === "in_review";
  const tone = status === "failed" ? "bad" : status === "approved" ? "neutral" : waiting ? "pending" : "neutral";
  return <span className={`badge s-${tone}`}>{CASE_LABELS[status] ?? status}</span>;
}

const VERDICTS: Record<string, string> = {
  high_suspicion: "High suspicion",
  partially_supported: "Partly supported",
  contradicted: "Contradicted",
  unverified: "Unverified",
};

/** The verdict in words, on a neutral badge: never a green "proven" or a red "guilty". */
export function VerdictBadge({ verdict }: { verdict: string }) {
  return <span className="verdict s-neutral" data-verdict={verdict}>{VERDICTS[verdict] ?? verdict}</span>;
}

export function ConfidenceMeter({ level }: { level: Confidence | string }) {
  const n = level === "high" ? 3 : level === "moderate" ? 2 : 1;
  return (
    <span className="row" style={{ gap: 6, display: "inline-flex" }} title={`${level} confidence`}>
      <span className="meter" aria-hidden>
        {[1, 2, 3].map((i) => <span key={i} className={i <= n ? "on" : ""} />)}
      </span>
      <span>{level} confidence</span>
    </span>
  );
}

export function percent(p: number | null | undefined): string {
  if (p == null) return "";
  if (p >= 0.995) return "over 99%";
  if (p < 0.005) return "under 1%";
  return `${Math.round(p * 100)}%`;
}
