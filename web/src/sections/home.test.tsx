import { screen, within } from "@testing-library/react";
import { setUser } from "../api/user";
import { renderAt } from "../test/render";
import { fakeApi, live, views } from "../test/server";

describe("the home page", () => {
  it("says why a new case cannot be opened when the server has no model", async () => {
    setUser("Amira");
    fakeApi();
    renderAt("/");
    expect(await screen.findByText(/No model is configured on the server/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Open case/ })).toBeDisabled();
  });

  it("lists what waits for a person, linked to where it is decided", async () => {
    fakeApi(undefined, {
      "/approvals": [
        { case_id: "C-PLAN", case_title: "t", ...live["C-PLAN"][""].pending_approvals[0] },
        { case_id: views["/cases"][0].id, case_title: "t", ...views["/approvals"][0] },
      ],
    });
    renderAt("/");
    const table = (await screen.findByRole("heading", { name: /Needs attention/ })).parentElement!;
    const links = await within(table).findAllByRole("link");
    expect(links.map((l) => l.getAttribute("href"))).toEqual([
      "/cases/C-PLAN/plan", `/cases/${views["/cases"][0].id}/casefile`]);
    expect(table).toHaveTextContent("Plan approval");
    expect(table).toHaveTextContent("Sign-off");
  });
});
