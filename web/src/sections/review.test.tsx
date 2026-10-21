import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setUser } from "../api/user";
import { renderAt } from "../test/render";
import { CASE_ID, fakeApi, views } from "../test/server";

const base = `/cases/${CASE_ID}`;

describe("hypotheses", () => {
  it("rank explanations by the evidence against them, untested apart, with the diagnostic rows first", async () => {
    fakeApi();
    renderAt(`${base}/hypotheses`);
    const matrix = await screen.findByRole("region", { name: "Matrix H3, H4, H5, H6, H7" });
    const cards = within(matrix).getAllByTestId(/^hypothesis-/).map((h) => h.dataset.testid);
    expect(cards).toEqual(["hypothesis-H3", "hypothesis-H4", "hypothesis-H5", "hypothesis-H6", "hypothesis-H7"]);
    expect(within(matrix).getByTestId("hypothesis-H3")).toHaveTextContent("least contradicted");
    expect(within(matrix).getByTestId("hypothesis-H5")).toHaveTextContent("untested");
    const firstRow = within(matrix).getAllByRole("row")[1];
    expect(firstRow).toHaveTextContent("◆ C9");
    expect(screen.getByText(/Ruled out, with the reason given/)).toBeInTheDocument();
  });
});

describe("the timeline", () => {
  it("flags the rewritten record", async () => {
    fakeApi();
    renderAt(`${base}/timeline`);
    const rewrite = await screen.findByTestId("event-rewrite");
    expect(rewrite).toHaveTextContent("Rewritten version observed");
    expect(rewrite).toHaveTextContent("amount_tnd ['120000000'] → ['80000000']");
  });
});

describe("the summary", () => {
  it("shows what was published, and every sentence removed with its reason", async () => {
    fakeApi();
    renderAt(`${base}/summary`);
    const published = await screen.findByRole("region", { name: "As published" });
    expect(published).not.toHaveTextContent("Karim");
    const rows = screen.getAllByTestId("sentence");
    const removed = rows.find((r) => r.textContent?.includes("Karim"))!;
    expect(removed.dataset.status).toBe("unsupported");
    expect(removed).toHaveTextContent("names Karim, Ben, Salah, which the cited sources do not name");
    expect(rows.map((r) => r.dataset.status)).toEqual(views["/cases/{id}/summary"].sentences.map((s: any) => s.status));
  });
});

describe("suspicions and the scope checkpoint", () => {
  it("lets a lawyer approve or reject a suspicion that names new companies", async () => {
    setUser("Maître Fictive");
    const suspicion = { id: "S1", statement: "Omega Conseil received subcontracts", status: "awaiting_scope",
      raised_by: "reviewer", round: 1, tested_by: null, confirm_by: "funder records", refute_by: "an erratum", tasks: [],
      new_entities: ["Société Omega Conseil"], note: "new people or companies", resolved_round: null };
    const { writes } = fakeApi(() => ({ body: { suspicions: [{ ...suspicion, status: "rejected" }] } }),
                               { "/cases/{id}/suspicions": { suspicions: [suspicion] } });
    const user = userEvent.setup();
    renderAt(`${base}/suspicions`);
    const card = await screen.findByRole("region", { name: "Wider scope: S1" });
    expect(card).toHaveTextContent("Société Omega Conseil");
    await user.click(within(card).getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(writes[0]).toMatchObject({ path: "/cases/{id}/suspicions/S1/scope",
                                                         body: { approve: false, note: "" }, user: "Maître Fictive" }));
  });
});

describe("the case file", () => {
  it("is signed off by a named editor, never edited", async () => {
    setUser("Sonia (editor)");
    const { writes } = fakeApi(() => ({ body: { ...views["/cases/{id}"], status: "approved" } }));
    const user = userEvent.setup();
    renderAt(`${base}/casefile`);
    const card = await screen.findByRole("region", { name: "Sign off the case file" });
    expect(await screen.findByRole("button", { name: "Open evidence E13" })).toBeInTheDocument(); // ids as chips
    expect(screen.queryByRole("textbox", { name: /case file/i })).not.toBeInTheDocument();
    await user.type(within(card).getByLabelText("Note for the ledger"), "checked the annexes");
    await user.click(within(card).getByRole("button", { name: "Sign off" }));
    await waitFor(() => expect(writes[0]).toEqual({ method: "POST", path: "/cases/{id}/sign-off",
                                                    body: { note: "checked the annexes" }, user: "Sonia (editor)" }));
  });
});

describe("the audit log", () => {
  it("shows the chain's integrity and filters by action", async () => {
    fakeApi();
    const user = userEvent.setup();
    renderAt(`${base}/audit`);
    expect(await screen.findByTestId("integrity")).toHaveTextContent(/Chain intact: \d+ entries/);
    const all = screen.getAllByTestId("ledger-entry").length;
    await user.selectOptions(screen.getByLabelText("Action"), "case_opened");
    expect(screen.getAllByTestId("ledger-entry")).toHaveLength(1);
    expect(all).toBeGreaterThan(1);
  });
});
