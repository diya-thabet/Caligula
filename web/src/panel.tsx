// The context panel's selection lives in the URL (?open=E13 or ?open=doc:jort_award_v1), so a view
// with a quote open can be shared or reloaded.
import { useSearchParams } from "react-router-dom";

export function usePanel() {
  const [params, setParams] = useSearchParams();
  const selected = params.get("open");
  const set = (value: string | null) =>
    setParams((p) => {
      const next = new URLSearchParams(p);
      if (value) next.set("open", value);
      else next.delete("open");
      return next;
    });
  return { selected, open: (id: string) => set(id), openDocument: (docId: string) => set(`doc:${docId}`), close: () => set(null) };
}
