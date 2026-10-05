import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";
import { api } from "./api/client";
import type { CaseEvent } from "./api/types";
import { currentUser, setUser } from "./api/user";

const LIVE = new Set(["preparing", "running", "paused"]);

export function useCase(id: string) {
  return useQuery({
    queryKey: ["case", id, "overview"],
    queryFn: () => api.overview(id),
    refetchInterval: (q) => (q.state.data && LIVE.has(q.state.data.status) ? 3000 : false),
  });
}

/** A case surface, refreshed whenever the case's live events say something happened. */
export function useCaseView<T>(id: string, name: string, fetcher: (id: string) => Promise<T>) {
  return useQuery({ queryKey: ["case", id, name], queryFn: () => fetcher(id) });
}

/**
 * Follow a case's events while it is open: every event refreshes the case's views (at most a few
 * times a second), and is handed to `onEvent` for the live tracker. The browser's EventSource
 * reconnects by itself and resumes after the last event seen.
 */
export function useLiveCase(id: string, onEvent?: (e: CaseEvent) => void) {
  const client = useQueryClient();
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource(api.streamUrl(id));
    let timer: ReturnType<typeof setTimeout> | null = null;
    const refresh = () => {
      if (timer) return;
      timer = setTimeout(() => {
        timer = null;
        client.invalidateQueries({ queryKey: ["case", id] });
        client.invalidateQueries({ queryKey: ["cases"] });
        client.invalidateQueries({ queryKey: ["approvals"] });
      }, 400);
    };
    const handle = (msg: MessageEvent) => {
      try {
        onEvent?.(JSON.parse(msg.data));
      } catch {
        /* ignore malformed frames */
      }
      refresh();
    };
    for (const kind of ["status", "phase", "tool", "audit", "error"]) source.addEventListener(kind, handle);
    return () => {
      source.close();
      if (timer) clearTimeout(timer);
    };
  }, [id, client, onEvent]);
}

// Who acts, shared by every component that needs it.
const listeners = new Set<() => void>();
export function useUser(): [string | null, (name: string) => void] {
  const user = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    currentUser,
  );
  return [user, (name: string) => {
    setUser(name);
    listeners.forEach((cb) => cb());
  }];
}
