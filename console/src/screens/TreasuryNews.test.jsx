import { readFileSync } from "node:fs";
import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import TreasuryNews from "./TreasuryNews.jsx";

// Mock the isolated news module (same-origin news.json fetch). The screen must render
// what it returns and must NOT reach into the console API / screening pipeline.
vi.mock("../lib/news.js", () => ({
  getNews: vi.fn(async () => ({
    generatedAt: "2026-07-11T18:00:00+00:00",
    items: [
      { source: "GAO", tier: "government", title: "Improper Payments Report", summary: "GAO found improper payments.", link: "https://www.gao.gov/x", date: "2026-07-10" },
      { source: "Federal Register", tier: "government", title: "Treasury Rule", summary: "A Treasury rule.", link: "https://www.federalregister.gov/y", date: "2026-07-11" },
      { source: "Politico", tier: "press", title: "A Politics Story", summary: "Some free press summary.", link: "https://www.politico.com/z", date: "2026-07-10" },
    ],
  })),
}));

describe("TreasuryNews", () => {
  test("groups items into Government and Press sections with tiered badges + last-updated", async () => {
    render(<TreasuryNews />);
    expect(await screen.findByText("Government sources")).toBeInTheDocument();
    expect(screen.getByText("Press")).toBeInTheDocument();
    expect(screen.getByText(/Last updated/)).toBeInTheDocument();
    // Government badge = accent (.gov); Press badge = neutral outline (.press)
    expect(screen.getByText("GAO")).toHaveClass("news-src", "gov");
    expect(screen.getByText("Politico")).toHaveClass("news-src", "press");
  });

  test("renders a safe external link and the summary", async () => {
    render(<TreasuryNews />);
    expect(await screen.findByText("GAO found improper payments.")).toBeInTheDocument();
    const link = screen.getByText("Read at GAO →").closest("a");
    expect(link).toHaveAttribute("href", "https://www.gao.gov/x");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  test("does not import the console API / screening pipeline", () => {
    // Static guard: the screen's only data dependency is lib/news.js. Inspect the IMPORT
    // lines only (so the isolation is proven by dependencies, not matched in a comment).
    const src = readFileSync("src/screens/TreasuryNews.jsx", "utf-8"); // vitest cwd = console/
    const imports = src.split("\n").filter((l) => /^\s*import\s/.test(l)).join("\n");
    expect(imports).toContain('from "../lib/news.js"');
    expect(imports).not.toContain("api.js"); // never the console_api client
    expect(imports).not.toMatch(/component_[a-g]|enrichment|disposition|risk_scoring|intake/);
  });
});
