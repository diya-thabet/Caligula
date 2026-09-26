import { usePanel } from "../panel";

/** An evidence id as a chip: opens the exact quote, search or amount in the context panel. */
export function Chip({ id }: { id: string }) {
  const { open } = usePanel();
  return (
    <button type="button" className="chip" onClick={() => open(id)} aria-label={`Open evidence ${id}`}>
      {id}
    </button>
  );
}

export function Chips({ ids, empty = "none" }: { ids: string[]; empty?: string }) {
  if (!ids.length) return <span className="faint">{empty}</span>;
  return <span className="row" style={{ gap: 4, display: "inline-flex" }}>{ids.map((id) => <Chip key={id} id={id} />)}</span>;
}
