import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setUser } from "../api/user";
import { renderAt } from "../test/render";
import { fakeApi, live } from "../test/server";

describe("the plan card", () => {
  it("is approved by a named person, recorded with the request", async () => {
    setUser("Amira (investigator)");
    const { writes } = fakeApi(() => ({ body: { ...live["C-PLAN"][""], status: "running" } }));
    const user = userEvent.setup();
    renderAt("/cases/C-PLAN/plan");
    const card = await screen.findByRole("region", { name: "Approve the plan" });
    expect(screen.getByLabelText("What code put back")).toHaveTextContent("What code added or changed in the plan");
    await user.type(within(card).getByLabelText("Note for the ledger"), "ok");
    await user.click(within(card).getByRole("button", { name: "Approve and start" }));
    await waitFor(() => expect(writes).toEqual([
      { method: "POST", path: "/cases/C-PLAN/plan/approve", body: {}, user: "Amira (investigator)" }]));
  });

  it("can be edited: tasks removed and added, then saved as planned tasks", async () => {
    setUser("Amira");
    const { writes } = fakeApi(() => ({ body: live["C-PLAN"]["/plan"] }));
    const user = userEvent.setup();
    renderAt("/cases/C-PLAN/plan");
    await user.click(await screen.findByRole("button", { name: /Edit tasks/ }));
    const editors = screen.getAllByTestId("task-editor");
    await user.click(within(editors[0]).getByRole("button", { name: "Remove task" }));
    await user.click(screen.getByRole("button", { name: /Add a task/ }));
    const added = screen.getAllByTestId("task-editor").at(-1)!;
    await user.type(within(added).getByLabelText("Objective"), "Search the lender's disbursement records");
    await user.click(screen.getByRole("button", { name: "Save the plan" }));
    await waitFor(() => expect(writes).toHaveLength(1));
    const [w] = writes;
    expect(w.method).toBe("PUT");
    expect(w.body.tasks).toHaveLength(editors.length);
    expect(w.body.tasks.at(-1)).toEqual({ specialist: "official", objective: "Search the lender's disbursement records",
                                          subclaim_ids: [], purpose: "support", queries: [], urls: [] });
  });

  it("cannot be approved by nobody", async () => {
    fakeApi();
    renderAt("/cases/C-PLAN/plan");
    const card = await screen.findByRole("region", { name: "Approve the plan" });
    expect(within(card).getByRole("button", { name: "Approve and start" })).toBeDisabled();
    expect(card).toHaveTextContent("Say who you are first");
  });

  it("shows the server's refusal when the case moved on", async () => {
    setUser("Amira");
    fakeApi(() => ({ status: 409, body: { detail: "case C-PLAN is running, not awaiting_plan_approval" } }));
    const user = userEvent.setup();
    renderAt("/cases/C-PLAN/plan");
    await user.click(await screen.findByRole("button", { name: "Approve and start" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("is running, not awaiting_plan_approval");
  });
});

describe("the legal checkpoint", () => {
  it("asks a lawyer to approve the scope, with a note", async () => {
    setUser("Maître Fictive");
    const { writes } = fakeApi(() => ({ body: live["C-LEGAL"][""] }));
    const user = userEvent.setup();
    renderAt("/cases/C-LEGAL");
    const card = await screen.findByRole("region", { name: "Legal review of the claim" });
    await user.type(within(card).getByLabelText("Note for the ledger"), "public contract");
    await user.click(within(card).getByRole("button", { name: "Approve the scope" }));
    await waitFor(() => expect(writes[0]).toEqual({ method: "POST", path: "/cases/C-LEGAL/legal-approval",
                                                    body: { note: "public contract" }, user: "Maître Fictive" }));
  });
});

describe("the activity tracker", () => {
  it("groups tool calls by round and agent, and shows code's refusals as the engine working", async () => {
    fakeApi();
    renderAt("/cases/C-RAN/activity");
    const round = await screen.findByRole("region", { name: "Round 1" });
    expect(within(round).getByText("official")).toBeInTheDocument();
    expect(within(round).getByText("reviewer")).toBeInTheDocument();
    const calls = within(round).getAllByTestId("tool-call").map((c) => c.textContent);
    expect(calls.some((t) => t?.includes("refused by code: Rejected: quote not found"))).toBe(true);
    const progress = screen.getByRole("region", { name: "Progress" });
    expect(progress).toHaveTextContent("in review — the round limit was reached");
    expect(progress).toHaveTextContent("round 1 closed: 0 task(s) done, 1 new evidence item(s); partially supported, low confidence");
  });
});
