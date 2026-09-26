import { findQuote, highlight } from "./text";
import { linkEvidence } from "./components/Markdown";

describe("quotes in stored text", () => {
  it("are found as validation finds them: case, spaces and no-break spaces do not matter", () => {
    const text = "Pour un montant de 120 000 000 TND,\npar procédure de GRÉ à gré.";
    const at = findQuote(text, "pour un  montant de 120 000 000 tnd");
    expect(at && text.slice(...at)).toBe("Pour un montant de 120 000 000 TND");
    expect(findQuote(text, "appel d'offres")).toBeNull();
  });

  it("are highlighted once each, the first of two overlapping quotes winning", () => {
    const parts = highlight("abc def ghi", [{ id: "E2", quote: "def ghi" }, { id: "E1", quote: "abc def" }]);
    expect(parts).toEqual([{ text: "abc def", id: "E1" }, { text: " ghi" }]);
  });
});

describe("evidence ids in Markdown", () => {
  it("become chips; expected-record ids and words do not", () => {
    expect(linkEvidence("For: E13, E14 (C5.E1) and EE1 or E2x")).toBe(
      "For: [E13](#evidence:E13), [E14](#evidence:E14) (C5.E1) and EE1 or E2x");
  });

  it("lose their citation brackets", () => {
    expect(linkEvidence("Worth 120M [E19]. Awarded [E13, E14].")).toBe(
      "Worth 120M [E19](#evidence:E19). Awarded [E13](#evidence:E13) [E14](#evidence:E14).");
  });
});
