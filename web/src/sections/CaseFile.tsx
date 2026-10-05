import { Download } from "lucide-react";
import { api } from "../api/client";
import { Checkpoint } from "../components/Checkpoint";
import { Markdown } from "../components/Markdown";
import { Query } from "../components/Query";
import { useCaseView } from "../hooks";
import { useCaseContext } from "./CaseLayout";

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

export function CaseFile() {
  const c = useCaseContext();
  const q = useCaseView(c.id, "report", api.report);
  return (
    <div className="stack">
      {c.status === "in_review" && (
        <Checkpoint caseId={c.id} title="Sign off the case file" role="editor" actions={[
          { label: "Sign off", primary: true, run: (note) => api.signOff(c.id, note) },
        ]}>
          The case file is built by code from the evidence and is not edited by hand. Signing off records your name, the time
          and the ledger's head, so any later change to the record can be detected. Check the annexes and the summary's
          sentence check first.
        </Checkpoint>
      )}
      {c.sign_off && (
        <div className="alert info">Approved by <b>{c.sign_off.by}</b> on {c.sign_off.at.slice(0, 16).replace("T", " ")}
          {c.sign_off.note && <> — {c.sign_off.note}</>}</div>
      )}
      <Query q={q}>
        {(text) => (
          <div className="stack">
            <div className="row">
              <span className="faint">{c.sign_off ? "Approved" : "Draft"} · Markdown, evidence ids preserved</span>
              <span className="spacer" />
              <button className="btn" onClick={() => download(`${c.id}.md`, text)}><Download size={14} /> Download</button>
            </div>
            <article className="card"><Markdown text={text} /></article>
          </div>
        )}
      </Query>
    </div>
  );
}
