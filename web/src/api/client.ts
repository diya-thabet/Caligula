import type {
  AnalysisView, AuditView, CaseEvent, CaseOverview, ClaimsView, DocumentFull, DocumentSummary, EvidenceItem, Health,
  HistoryView, PlannedTask, PlanView, QueueItem, Suspicion, SummaryView, TimelineEvent, Versions,
} from "./types";
import { currentUser } from "./user";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body) headers["Content-Type"] = "application/json";
  if (init.method && init.method !== "GET") {
    const user = currentUser();
    // Headers are ASCII: the name travels URL-encoded (see docs/api.md).
    if (user) headers["X-Caligula-User"] = encodeURIComponent(user);
  }
  const res = await fetch(`/api${path}`, { ...init, headers: { ...headers, ...(init.headers ?? {}) } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

const post = <T>(path: string, body: unknown = {}) => request<T>(path, { method: "POST", body: JSON.stringify(body) });
const c = (id: string) => `/cases/${encodeURIComponent(id)}`;

export const api = {
  health: () => request<Health>("/health"),
  cases: () => request<CaseOverview[]>("/cases"),
  approvals: () => request<QueueItem[]>("/approvals"),
  openCase: (claim: string, mode: string, poc: boolean) => post<CaseOverview>("/cases", { claim, mode, poc }),
  overview: (id: string) => request<CaseOverview>(c(id)),
  analysis: (id: string) => request<AnalysisView>(`${c(id)}/analysis`),
  claims: (id: string) => request<ClaimsView>(`${c(id)}/claims`),
  evidence: (id: string) => request<{ items: EvidenceItem[] }>(`${c(id)}/evidence`),
  documents: (id: string) => request<{ documents: DocumentSummary[] }>(`${c(id)}/documents`),
  document: (id: string, docId: string) => request<DocumentFull>(`${c(id)}/documents/${encodeURIComponent(docId)}`),
  versions: (id: string, docId: string) =>
    request<Versions>(`${c(id)}/documents/${encodeURIComponent(docId)}/versions`),
  timeline: (id: string) => request<{ events: TimelineEvent[] }>(`${c(id)}/timeline`),
  suspicions: (id: string) => request<{ suspicions: Suspicion[] }>(`${c(id)}/suspicions`),
  audit: (id: string) => request<AuditView>(`${c(id)}/audit`),
  summary: (id: string) => request<SummaryView>(`${c(id)}/summary`),
  history: (id: string) => request<HistoryView>(`${c(id)}/history`),
  report: (id: string) => request<string>(`${c(id)}/report`, { headers: { Accept: "text/markdown" } }),
  plan: (id: string) => request<PlanView>(`${c(id)}/plan`),
  events: (id: string, after = 0) => request<CaseEvent[]>(`${c(id)}/events?after=${after}`),
  editPlan: (id: string, tasks: PlannedTask[]) =>
    request<PlanView>(`${c(id)}/plan`, { method: "PUT", body: JSON.stringify({ tasks }) }),
  approvePlan: (id: string) => post<CaseOverview>(`${c(id)}/plan/approve`),
  approveLegal: (id: string, note: string) => post<CaseOverview>(`${c(id)}/legal-approval`, { note }),
  pause: (id: string) => post<CaseOverview>(`${c(id)}/pause`),
  resume: (id: string) => post<CaseOverview>(`${c(id)}/resume`),
  stop: (id: string) => post<CaseOverview>(`${c(id)}/stop`),
  decideScope: (id: string, sid: string, approve: boolean, note: string) =>
    post<{ suspicions: Suspicion[] }>(`${c(id)}/suspicions/${sid}/scope`, { approve, note }),
  signOff: (id: string, note: string) => post<CaseOverview>(`${c(id)}/sign-off`, { note }),
  streamUrl: (id: string) => `/api${c(id)}/events/stream`,
};
