import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Chip } from "./Chip";

// Evidence ids (E13), bare or cited in brackets ([E3, E7]), become chips; expected-record ids
// (C5.E1) do not. Raw HTML in the Markdown is never rendered: case files quote scraped pages.
const EVIDENCE = /\[(E\d+(?:\s*,\s*E\d+)*)\]|(?<![.\w[])(E\d+)\b/g;

export function linkEvidence(markdown: string): string {
  return markdown.replace(EVIDENCE, (_, group: string | undefined, bare: string | undefined) =>
    (group ? group.split(/\s*,\s*/) : [bare!]).map((id) => `[${id}](#evidence:${id})`).join(" "));
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) =>
            href?.startsWith("#evidence:") ? <Chip id={href.slice("#evidence:".length)} /> : (
              <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>
            ),
        }}
      >
        {linkEvidence(text)}
      </ReactMarkdown>
    </div>
  );
}
