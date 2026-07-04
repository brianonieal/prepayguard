// Client-side audit-record integrity verification.
// canonicalize() reproduces Python's json.dumps(sort_keys=True,
// separators=(",",":")) for ASCII data, so the browser can recompute the same
// SHA-256 the pipeline wrote. (Cross-language canonicalization caveat for
// v1.4.0: float formatting e.g. 75.0 vs 75 and non-ASCII escaping must match
// Python exactly, or verification of live records will false-negative.)
export function canonicalize(v) {
  if (v === null) return "null";
  if (Array.isArray(v)) return "[" + v.map(canonicalize).join(",") + "]";
  if (typeof v === "object") {
    return "{" + Object.keys(v).sort()
      .map((k) => JSON.stringify(k) + ":" + canonicalize(v[k])).join(",") + "}";
  }
  return JSON.stringify(v);
}

export async function sha256Hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Hash of the record excluding its own `integrity` block, matches the
// pipeline's "all fields except integrity, sorted-key compact JSON".
export async function hashRecord(record) {
  const { integrity: _omit, ...rest } = record;
  return sha256Hex(canonicalize(rest));
}
