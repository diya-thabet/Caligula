import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderAt } from "../test/render";
import { CASE_ID, fakeApi } from "../test/server";

const base = `/cases/${CASE_ID}`;

describe("the case header", () => {
  it("states the verdict in words, the likelihood and the confidence, never a bare percentage", async () => {
    fakeApi();
    renderAt(base);
    const a = await screen.findByTestId("assessment");
    expect(a).toHaveTextContent("High suspicion");
    expect(a).toHaveTextContent("core facts very likely");
    expect(a).toHaveTextContent("moderate confidence");
    expect(a).toHaveTextContent("final");
    expect(a.textContent).not.toMatch(/%/);
    expect(screen.getByRole("note")).toHaveTextContent("Proof of concept");
    expect(screen.getByText("Draft")).toBeInTheDocument();
  });
});

describe("the overview", () => {
  it("puts the bottom line first and flags the rewritten record", async () => {
    fakeApi();
    renderAt(base);
    const headings = await screen.findAllByRole("heading", { level: 2 });
    expect(headings.map((h) => h.textContent)).toEqual([
      "Bottom line", "Key judgments", "Alternatives considered", "Key assumptions",
      "What the conclusion depends on", "Gaps and collection requests", "Indicators that would change the assessment"]);
    expect(await screen.findByText("Record rewritten")).toBeInTheDocument();
  });
});

describe("claim cards and citation chips", () => {
  it("show each judgment with its evidence, and a chip opens the exact quote in its document", async () => {
    fakeApi();
    const user = userEvent.setup();
    renderAt(`${base}/claims`);
    const c5 = await screen.findByTestId("claim-C5");
    expect(c5).toHaveTextContent("almost certain true");
    expect(c5).toHaveTextContent("never challenged");
    await user.click(within(c5).getByRole("button", { name: "Open evidence E13" }));
    const panel = await screen.findByRole("complementary", { name: "Context" });
    expect(within(panel).getByText("« par procédure de gré à gré »")).toBeInTheDocument();
    const text = await within(panel).findByTestId("document-text");
    await waitFor(() => expect(text.querySelector('mark[data-evidence="E13"]')).toHaveTextContent("par procédure de gré à gré"));
    expect(within(panel).getByText(/Stored bytes match their recorded hash/)).toBeInTheDocument();
  });

  it("explain how a judgment was concluded from computed values", async () => {
    fakeApi();
    const user = userEvent.setup();
    renderAt(`${base}/claims`);
    const c6 = await screen.findByTestId("claim-C6");
    await user.click(within(c6).getByRole("button", { name: /How this was concluded/ }));
    expect(c6).toHaveTextContent("Without benchmark: C6 supported → unverified");
  });

  it("filter to what nobody has challenged", async () => {
    fakeApi();
    const user = userEvent.setup();
    renderAt(`${base}/claims`);
    await screen.findByTestId("claim-C2");
    await user.click(screen.getByLabelText("never challenged"));
    expect(screen.queryByTestId("claim-C2")).not.toBeInTheDocument(); // contradicted: not a candidate
    expect(screen.getByTestId("claim-C5")).toBeInTheDocument();
  });
});

describe("evidence and documents", () => {
  it("lists every item by id with its source's reliability, and marks a party's own claim", async () => {
    fakeApi();
    renderAt(`${base}/evidence`);
    const row = (await screen.findByRole("button", { name: "Open evidence E16" })).closest("tr")!;
    expect(row).toHaveTextContent("party");
    expect(row).toHaveTextContent("live official page (editable by its publisher)");
  });

  it("compares the versions of a rewritten record", async () => {
    fakeApi();
    const user = userEvent.setup();
    renderAt(`${base}/documents?open=doc:jort_award_v1`);
    const panel = await screen.findByRole("complementary", { name: "Context" });
    await user.click(await within(panel).findByRole("button", { name: /Compare versions/ }));
    await waitFor(() => expect(panel).toHaveTextContent("jort_award_v1 → jort_award_v2: amount_tnd 120000000 → 80000000"));
  });
});
