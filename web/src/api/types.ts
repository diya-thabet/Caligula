// Shapes of the API's JSON views (src/caligula/adapters/presenters/case_views.py).

export type CaseStatus =
  | "refused" | "awaiting_legal_review" | "preparing" | "awaiting_plan_approval"
  | "running" | "paused" | "in_review" | "approved" | "failed";

export type SubclaimStatus = "supported" | "contradicted" | "contested" | "partially_supported" | "unverified";
export type Confidence = "low" | "moderate" | "high";
export type Relation = "supports" | "contradicts" | "qualifies";

export interface Assessment {
  verdict: string;
  likelihood: number | null;
  likelihood_term: string;
  confidence: Confidence;
  confidence_reasons: string[];
  final: boolean;
}

export interface Approval {
  kind: "legal_review" | "plan_approval" | "scope" | "sign_off";
  role: "lawyer" | "investigator" | "editor";
  about: string;
  suspicion?: string;
  entities?: string[];
}

export interface Party { name: string; role: "accused" | "complainant"; aliases: string[] }

export interface CaseOverview {
  id: string;
  claim: string;
  title: string;
  status: CaseStatus;
  note: string;
  mode: "factcheck" | "investigate";
  poc: boolean;
  created_by: string;
  created_at: string;
  last_activity: string;
  claim_type: string | null;
  parties: Party[];
  assessment: Assessment | null;
  stop_reason: string | null;
  rounds: number;
  counts: null | {
    documents: number; evidence: number; pending_proposals: number; open_tasks: number;
    tool_calls: number; open_suspicions: number;
  };
  pending_approvals: Approval[];
  sign_off: null | { by: string; at: string; note: string };
}

export interface QueueItem extends Approval { case_id: string; case_title: string }

export interface Health { status: string; can_investigate: boolean; cases: number }

export interface Task {
  id: string; specialist: string; objective: string; subclaim_ids: string[];
  purpose: "support" | "challenge" | "explore"; queries: string[]; urls: string[]; round: number;
  created_by: string; expectation_id: string | null; suspicion_id: string | null;
  status: "open" | "done"; outcome: "found" | "partial" | "not_found" | "blocked" | null; note: string;
  doc_ids: string[];
}

export interface PlannedTask {
  specialist: string; objective: string; subclaim_ids: string[]; purpose: Task["purpose"];
  queries: string[]; urls: string[]; expectation_id?: string | null;
}

export interface PlanView {
  status: CaseStatus;
  editable?: boolean;
  plan?: null;
  entities?: { name: string; kind: string; aliases: string[] }[];
  window?: [string | null, string | null];
  budgets?: Record<string, number>;
  fixes?: string[];
  tasks?: Task[];
}

export interface ExpectedRecord { description: string; register_id: string; absence_means: Relation }

export interface SubclaimCard {
  id: string; statement: string; core: boolean; bearing: "against" | "for" | "neutral";
  status: SubclaimStatus; likelihood: number | null; likelihood_term: string; confidence: Confidence;
  confidence_reasons: string[]; support: number; contradiction: number;
  independent_origins: { for: number; against: number };
  evidence: Record<Relation, string[]>; challenged: boolean; verification_questions: string[];
  expected_records: ExpectedRecord[];
}

export interface HypothesisCard {
  id: string; kind: "allegation" | "innocent" | "alternative"; statement: string;
  status: "consistent" | "falsified" | "open"; reasons: string[]; predicts: Record<string, boolean>;
  evidence_against: number | null; untested: boolean;
}

export interface Dependency { origin: string[]; changes: string[]; changes_verdict: boolean }

export interface ClaimsView {
  subclaims: SubclaimCard[];
  hypotheses: HypothesisCard[];
  ruled_out: { explanation_id: string; reason: string }[];
  depends_on?: Dependency[];
}

export interface Source {
  doc_id: string; publisher: string; kind: string; reliability: string;
  published_at: string | null; observed_at: string; url: string;
}

export interface EvidenceItem {
  evidence_id: string | null; proposal_id: string | null;
  status: "pending" | "accepted" | "disputed"; proposed_by: string | null; review_note: string; counts: boolean;
  type: "quote" | "amount" | "absence";
  subclaim_id?: string; relation?: Relation; quote?: string; source?: Source; origin?: string;
  weight?: number | null; publisher_interest?: "none" | "self_serving" | "against_interest";
  role?: string; amount_tnd?: number; used_by_financial_check?: boolean;
  register?: string; register_name?: string; query?: string; searched_at?: string; capture?: string | null;
}

export interface Custody {
  raw_sha256: string; text_sha256: string; extraction: string; cites: string[]; derived_from: string[];
  captured: { seq: number; at: string; actor: string; data: Record<string, unknown> }[];
  bytes_intact: boolean;
}

export interface DocumentSummary extends Source {
  title: string; canonical_url: string; used_by: string[]; custody: Custody;
}

export interface DocumentFull extends DocumentSummary {
  text: string; highlights: { evidence_id: string; quote: string }[];
}

export interface Versions {
  canonical_url: string;
  versions: (Source & { text: string; extraction: string })[];
  changes: { from: string; to: string; changes: { kind: string; removed: string[]; added: string[] }[] }[];
}

export interface TimelineEvent {
  date: string; type: "document" | "claimed_event" | "rewrite"; text: string; doc_id?: string;
  earlier_doc_id?: string; subclaim_id?: string; source?: Source; first_seen?: string; seen_late?: boolean;
  needs_review?: boolean;
}

export interface Suspicion {
  id: string; statement: string; status: "open" | "confirmed" | "refuted" | "awaiting_scope" | "rejected";
  raised_by: string; round: number; tested_by: string | null; confirm_by: string; refute_by: string;
  tasks: string[]; new_entities: string[]; note: string; resolved_round: number | null;
}

export interface AuditEntry { seq: number; at: string; action: string; actor: string; data: Record<string, unknown>; hash: string }

export interface AuditView {
  integrity: { entries: number; head: string; intact: boolean; broken_at: number | null };
  entries: AuditEntry[];
}

export type SentenceStatus = "supported" | "partial" | "unsupported" | "uncited" | "unjudged" | "analysis";

export interface SummaryView {
  written: string | null;
  published: string | null;
  sentences: { text: string; status: SentenceStatus; cited: string[]; reasons: string[] }[];
}

export interface AnalysisView { sections: { title: string; markdown: string }[]; final?: boolean }

export interface Round {
  round: number; specialists: string[]; tasks_closed: Record<string, string>; new_evidence: number;
  accepted: number; disputed: number; suspicions_raised: string[]; suspicions_resolved: Record<string, string>;
  verdict: string; confidence: string; statuses: Record<string, string>; tool_calls: number;
}

export interface HistoryView { rounds: Round[]; stop_reason: string | null; stop_explained: string | null }

export interface CaseEvent {
  seq: number; at: string; kind: "status" | "phase" | "tool" | "audit" | "error"; data: Record<string, any>;
}
