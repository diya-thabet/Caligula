import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Topbar } from "./components/Topbar";
import { CaseLayout } from "./sections/CaseLayout";
import { Home } from "./sections/Home";
import { SECTIONS } from "./sections/registry";

export function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 2000, refetchOnWindowFocus: false } } });
}

export function Routed() {
  return (
    <div className="app">
      <Topbar />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/cases/:caseId" element={<CaseLayout />}>
          {SECTIONS.map((s) => (
            <Route key={s.path} index={s.path === ""} path={s.path || undefined} element={<s.Component />} />
          ))}
        </Route>
        <Route path="*" element={<div className="empty">Nothing here. <a href="/">Back to the cases.</a></div>} />
      </Routes>
    </div>
  );
}

export function App({ client = makeClient() }: { client?: QueryClient }) {
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <Routed />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
