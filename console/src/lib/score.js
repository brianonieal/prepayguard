// Mirror of Component C's rule-based scoring (DEC-14), for reviewer-facing
// explainability: show WHY a payment landed where it did.
const WEIGHT = { high: 1.0, medium: 0.6, low: 0.3 };
const NAME_MATCH_CAP = 60;

export function explainScore(audit) {
  const matches = audit?.evidence?.matches || [];
  let best = 0;
  const steps = matches.map((m) => {
    const weight = WEIGHT[m.severity] ?? 1.0;
    const raw = m.confidence * weight;
    const value = m.matched_on === "tin" ? raw : Math.min(raw, NAME_MATCH_CAP);
    best = Math.max(best, value);
    return {
      ...m,
      weight,
      raw: Math.round(raw),
      value: Math.round(value),
      capped: m.matched_on !== "tin" && raw > NAME_MATCH_CAP,
    };
  });
  best = Math.round(best);
  const band = best >= 80 ? "reject" : best >= 30 ? "review" : "approve";
  return { best, band, steps };
}
