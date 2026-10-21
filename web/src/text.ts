// Quotes are validated after normalisation (case, spaces, no-break spaces), so they are found in
// the stored text the same way, then mapped back to the original characters for highlighting.
function normalizeChar(ch: string): string {
  return /\s/.test(ch) || ch === " " || ch === " " ? " " : ch.toLowerCase();
}

export function findQuote(text: string, quote: string): [number, number] | null {
  const norm: string[] = [];
  const index: number[] = [];
  for (let i = 0; i < text.length; i++) {
    const ch = normalizeChar(text[i]);
    if (ch === " " && norm[norm.length - 1] === " ") continue;
    norm.push(ch);
    index.push(i);
  }
  const needle = quote.split("").map(normalizeChar).join("").replace(/ +/g, " ").trim();
  if (!needle) return null;
  const at = norm.join("").indexOf(needle);
  if (at < 0) return null;
  return [index[at], index[at + needle.length - 1] + 1];
}

/** Text split into plain and highlighted parts, one highlight per quote found (earliest first). */
export function highlight(text: string, quotes: { id: string; quote: string }[]) {
  const spans = quotes
    .map((q) => ({ id: q.id, at: findQuote(text, q.quote) }))
    .filter((s): s is { id: string; at: [number, number] } => s.at !== null)
    .sort((a, b) => a.at[0] - b.at[0]);
  const parts: { text: string; id?: string }[] = [];
  let pos = 0;
  for (const s of spans) {
    if (s.at[0] < pos) continue; // overlapping quotes: the first one wins
    if (s.at[0] > pos) parts.push({ text: text.slice(pos, s.at[0]) });
    parts.push({ text: text.slice(s.at[0], s.at[1]), id: s.id });
    pos = s.at[1];
  }
  if (pos < text.length) parts.push({ text: text.slice(pos) });
  return parts;
}
