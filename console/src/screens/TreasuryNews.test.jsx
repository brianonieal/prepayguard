import { readFileSync } from "node:fs";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import TreasuryNews from "./TreasuryNews.jsx";

// Mock the isolated news module. The screen must render + filter what it returns and must
// NOT reach into the console API / screening pipeline.
vi.mock("../lib/news.js", () => ({
  getNews: vi.fn(async () => ({
    generatedAt: "2026-07-11T18:00:00+00:00",
    items: [
      { source: "GAO", tier: "government", title: "Improper Payments Report", summary: "GAO found improper payments in Medicare.", link: "https://www.gao.gov/x", date: "2026-07-10" },
      { source: "Federal Register", tier: "government", title: "Treasury Rule on Trusts", summary: "A Treasury rule.", link: "https://www.federalregister.gov/y", date: "2026-07-11" },
      { source: "Politico", tier: "press", title: "A Politics Story", summary: "Some free press summary.", link: "https://www.politico.com/z", date: "2026-07-09" },
    ],
  })),
}));

describe("TreasuryNews", () => {
  test("empty search shows Government + Press sections with tiered badges + last-updated", async () => {
    render(<TreasuryNews />);
    expect(await screen.findByText("Government sources")).toBeInTheDocument();
    expect(screen.getByText("Press")).toBeInTheDocument();
    expect(screen.getByText(/Last updated/)).toBeInTheDocument();
    expect(screen.getByText("GAO")).toHaveClass("news-src", "gov");     // Government = accent
    expect(screen.getByText("Politico")).toHaveClass("news-src", "press"); // Press = neutral outline
  });

  test("a query flattens both tiers into a single Results list with a count", async () => {
    render(<TreasuryNews />);
    await screen.findByText("Government sources");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "improper payments" } });
    expect(screen.getByText("Results")).toBeInTheDocument();
    expect(screen.queryByText("Government sources")).not.toBeInTheDocument(); // sections collapse to Results
    expect(screen.getByText(/1 result for "improper payments"/)).toBeInTheDocument();
    expect(screen.getByText("Improper Payments Report")).toBeInTheDocument();
    expect(screen.queryByText("A Politics Story")).not.toBeInTheDocument();
  });

  test("search matches the source name, and shows a clean empty state on no match", async () => {
    render(<TreasuryNews />);
    await screen.findByText("Government sources");
    const box = screen.getByRole("searchbox");
    fireEvent.change(box, { target: { value: "politico" } });
    expect(screen.getByText("A Politics Story")).toBeInTheDocument(); // matched by source name
    fireEvent.change(box, { target: { value: "zzz-nothing" } });
    expect(screen.getByText(/No news items match "zzz-nothing"/)).toBeInTheDocument();
  });

  test("view toggle switches views client-side without losing content", async () => {
    render(<TreasuryNews />);
    await screen.findByText("Government sources");
    for (const v of ["Grid", "Magazine", "List"]) {
      fireEvent.click(screen.getByRole("button", { name: v }));
      expect(screen.getByRole("button", { name: v })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByText("Improper Payments Report")).toBeInTheDocument(); // content survives
    }
  });

  test("renders a safe external link (list view)", async () => {
    render(<TreasuryNews />);
    const link = (await screen.findByText(/Read at GAO/)).closest("a");
    expect(link).toHaveAttribute("href", "https://www.gao.gov/x");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  test("does not import the console API / screening pipeline", () => {
    const src = readFileSync("src/screens/TreasuryNews.jsx", "utf-8"); // vitest cwd = console/
    const imports = src.split("\n").filter((l) => /^\s*import\s/.test(l)).join("\n");
    expect(imports).toContain('from "../lib/news.js"');
    expect(imports).not.toContain("api.js");
    expect(imports).not.toMatch(/component_[a-g]|enrichment|disposition|risk_scoring|intake/);
  });
});
