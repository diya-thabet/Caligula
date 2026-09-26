import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

/** Loading, error and data states, said plainly. */
export function Query<T>({ q, children }: { q: UseQueryResult<T>; children: (data: T) => ReactNode }) {
  if (q.isPending) return <div className="faint" role="status">Loading…</div>;
  if (q.isError) return <div className="error-text" role="alert">Could not load: {(q.error as Error).message}</div>;
  return <>{children(q.data)}</>;
}

export function ago(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toISOString().slice(0, 10);
}
