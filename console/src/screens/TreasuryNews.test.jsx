import { readFileSync } from "node:fs";
import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import TreasuryNews from "./TreasuryNews.jsx";

// Mock the isolated news module (same-origin news.json fetch). The screen must render
// what it returns and must NOT reach into the console API / screening pipeline.
vi.mock("../lib/news.js", () => ({
  getNews: vi.fn(async () => [
    { source: "GAO", title: "Improper Payments Report", summary: "GAO found improper payments.", link: "https://www.gao.gov/x", date: "2026-07-10" },
    { source: "Federal Register", title: "Treasury Rule", summary: "A Treasury rule.", link: "https://www.federalregister.gov/y", date: "2026-07-11" },
  ]),
}));

describe("TreasuryNews", () => {
  test("renders items with source badge, title, summary, and a safe external link", async () => {
    render(<TreasuryNews />);
    expect(await screen.findByText("Improper Payments Report")).toBeInTheDocument();
    expect(screen.getByText("GAO")).toBeInTheDocument();
    expect(screen.getByText("GAO found improper payments.")).toBeInTheDocument();

    const link = screen.getByText("Read at GAO →").closest("a");
    expect(link).toHaveAttribute("href", "https://www.gao.gov/x");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  test("does not import the console API / screening pipeline", async () => {
    // Static guard: the screen's only data dependency is lib/news.js. Inspect the IMPORT
    // lines only (so the isolation is proven by dependencies, not matched in a comment).
    const src = readFileSync("src/screens/TreasuryNews.jsx", "utf-8"); // vitest cwd = console/
    const imports = src.split("\n").filter((l) => /^\s*import\s/.test(l)).join("\n");
    expect(imports).toContain('from "../lib/news.js"');
    expect(imports).not.toContain("api.js"); // never the console_api client
    expect(imports).not.toMatch(/component_[a-g]|enrichment|disposition|risk_scoring|intake/);
  });
});
