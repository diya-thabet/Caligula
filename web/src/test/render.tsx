import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { makeClient, Routed } from "../App";

export function renderAt(path: string) {
  const client = makeClient();
  client.setDefaultOptions({ queries: { retry: false, staleTime: Infinity } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}><Routed /></MemoryRouter>
    </QueryClientProvider>,
  );
}
