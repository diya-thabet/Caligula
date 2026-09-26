import { api } from "../api/client";
import { Chips } from "../components/Chip";
import { Markdown } from "../components/Markdown";
import { Query } from "../components/Query";
import { StatusBadge } from "../components/status";
import { useCaseView } from "../hooks";
import { useCaseContext } from "./CaseLayout";

const WHY: Record<string, string> = {
  supported: "the judge found it in the cited quotes",
  partial: "partly in the cited quotes: published with a mark",
  unsupported: "removed: its evidence does not say it",
  uncited: "removed: a fact without evidence",
  unjudged: "passed the checks in code; no judge model read it",
  analysis: "the writer's analysis: no fact to check",
};

export function Summary() {
  const c = useCaseContext();
  const q = useCaseView(c.id, "summary", api.summary);
  return (
    <Query q={q}>
      {(s) => !s.written ? <div className="empty">No summary yet: the reviewer writes it at the end of each round.</div> : (
        <div className="stack">
          <section className="card stack" aria-label="As published">
            <b>As published, after the citation check</b>
            <Markdown text={s.published || "(nothing left after the check)"} />
          </section>
          <section className="stack" aria-label="Sentence check">
            <h3>Sentence check</h3>
            <div className="faint">Every factual sentence must cite the evidence it rests on. Code checks figures, references
              and names against the cited evidence; a judge model then reads each sentence against its quotes. Sentences that
              fail are removed here, never silently.</div>
            <div className="table-wrap"><table>
              <thead><tr><th>#</th><th>Sentence</th><th>Cites</th><th>Check</th><th>Why</th></tr></thead>
              <tbody>{s.sentences.map((x, i) => (
                <tr key={i} data-testid="sentence" data-status={x.status}>
                  <td className="faint">{i + 1}</td>
                  <td style={{ maxWidth: 420, textDecoration: x.status === "unsupported" || x.status === "uncited" ? "line-through" : undefined }}>
                    {x.text}</td>
                  <td><Chips ids={x.cited} empty="–" /></td>
                  <td><StatusBadge status={x.status} /></td>
                  <td className="small muted">{x.reasons.join("; ") || WHY[x.status]}</td>
                </tr>))}
              </tbody></table></div>
          </section>
          <details className="card small"><summary>As the reviewer wrote it</summary><p>{s.written}</p></details>
        </div>
      )}
    </Query>
  );
}
