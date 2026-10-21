import { api } from "../api/client";
import { Checkpoint } from "../components/Checkpoint";
import { useCaseContext } from "./CaseLayout";

/** The claim needs a lawyer's approval of its scope before any agent runs. */
export function LegalCheckpoint() {
  const c = useCaseContext();
  if (c.status !== "awaiting_legal_review") return null;
  return (
    <Checkpoint caseId={c.id} title="Legal review of the claim" role="lawyer" actions={[
      { label: "Approve the scope", primary: true, run: (note) => api.approveLegal(c.id, note) },
    ]}>
      The intake policy asks for a lawyer before this claim is investigated: {c.note || "see the audit log"}.
      Approving lets the analyst decompose the claim and draft a plan; nothing runs until the plan is approved.
    </Checkpoint>
  );
}
