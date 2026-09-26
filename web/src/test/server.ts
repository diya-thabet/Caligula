// A fake API for the interface's tests: every GET answers from steg.json (taken from the real API
// by tests/adapters/test_web_fixture.py); writes are recorded and answered by `onWrite`.
import { vi } from "vitest";
import steg from "./steg.json";

export const CASE_ID: string = steg.case_id;
export const views = steg.views as Record<string, any>;

export interface Write { method: string; path: string; body: any; user: string | null }

export function fakeApi(onWrite: (w: Write) => { status?: number; body: any } = () => ({ body: {} }),
                        overrides: Record<string, any> = {}) {
  const writes: Write[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input), "http://test");
    const path = decodeURIComponent(url.pathname.replace(/^\/api/, "")).replace(CASE_ID, "{id}");
    const method = init.method ?? "GET";
    const json = (status: number, body: any) =>
      new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
    if (method !== "GET") {
      const headers = (init.headers ?? {}) as Record<string, string>;
      const w = { method, path, body: init.body ? JSON.parse(String(init.body)) : null,
                  user: headers["X-Caligula-User"] ? decodeURIComponent(headers["X-Caligula-User"]) : null };
      writes.push(w);
      const r = onWrite(w);
      return json(r.status ?? 200, r.body);
    }
    if (path in overrides) return json(200, overrides[path]);
    if (path === "/cases/{id}/report") {
      return new Response("# Case\n\n## Bottom line\n\nHigh suspicion [E13].", { headers: { "content-type": "text/markdown" } });
    }
    if (path in views) return json(200, views[path]);
    return json(404, { detail: `no fake for ${path}` });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { writes, fetchMock };
}
