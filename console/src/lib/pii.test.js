import { describe, expect, test } from "vitest";
import { maskIndividualName, maskName, looksLikeEntity, normName, redactName } from "./pii.js";

describe("maskIndividualName → 'First L.' format", () => {
  test.each([
    ["James O. Wilson Jr.", "James W."],
    ["ARNITA LEFF", "ARNITA L."],
    ["Michael KUAJIEN", "Michael K."],
    ["Haresh K. Mirani", "Haresh M."],
    ["RENEE MICHELE HAAS", "RENEE H."],
    ["EDEDEM EDEM", "EDEDEM E."],
    ["DARRON BROADUS SR", "DARRON B."],
  ])("%s → %s", (input, expected) => {
    expect(maskIndividualName(input)).toBe(expected);
  });
});

describe("entity heuristic keeps companies full (unlisted names)", () => {
  test.each([
    "Hawwk LLC", "Globex Offshore Inc", "YATAI SMART INDUSTRIAL NEW CITY",
    "CFK, INC", "Top Notch Construction", "Coast Medical Supply",
    "REGENTS OF THE UNIVERSITY OF CALIFORNIA, THE", "LOCKHEED MARTIN CORP",
  ])("entity: %s", (name) => {
    expect(looksLikeEntity(name)).toBe(true);
    expect(maskName(name, null, null)).toBe(name); // no map, heuristic → full
  });
});

describe("classification field overrides the heuristic (authoritative)", () => {
  test("Individual classification masks even a company-shaped name", () => {
    // heuristic would call this an entity ("Co"); the classification field wins → masked
    expect(maskName("Acme Trading Co", "Individual", null)).toBe("Acme C.");
  });
  test("Entity classification keeps a person-shaped name full", () => {
    // (defensive — no such data today, but the field wins if present)
    expect(maskName("John Smith", "Entity", null)).toBe("John Smith");
  });
  test("reference map resolves a listed single-word entity that the heuristic would miss", () => {
    const map = new Map([[normName("NURKEZ"), "Entity"], [normName("Michael Ross"), "Individual"]]);
    expect(maskName("NURKEZ", undefined, map)).toBe("NURKEZ");        // map says Entity → full
    expect(maskName("Michael Ross", undefined, map)).toBe("Michael R."); // map says Individual → mask
  });
  test("null (synthetic seed) in the map shows full", () => {
    const map = new Map([[normName("John Q Public"), null]]);
    expect(maskName("John Q Public", undefined, map)).toBe("John Q Public");
  });
});

describe("brief redaction removes the individual's surname from prose", () => {
  test("full name and standalone surname are redacted; first name kept", () => {
    const brief = "The payment to James O. Wilson Jr. matched a listed entity; Wilson appears on SAM.";
    const out = redactName(brief, "James O. Wilson Jr.", "Individual", null);
    expect(out).not.toMatch(/Wilson/);
    expect(out).toContain("James");
  });
  test("entity payee prose is left untouched", () => {
    const brief = "The payment to Hawwk LLC matched SAM exclusions.";
    expect(redactName(brief, "Hawwk LLC", "Entity", null)).toBe(brief);
  });
});
