// PII masking (UI layer only — never alters stored data or the matcher).
//
// Real INDIVIDUAL-PERSON names must not render on the public console surface next
// to a Do Not Pay source. Companies/entities and the fabricated synthetic seeds
// render in full. The authoritative signal is the reference entry's `classification`
// field ("Individual" | "Entity"); the deployed v4 list carries it for every real
// entry (synthetic seeds are null → shown full). Where a surface only has a bare
// payee name (review queue, audit, showcase, batch preview), we resolve the name
// against the reference classification map; for a name not on any list we fall back
// to a conservative entity heuristic (mask unless it clearly reads as an org).
import { useCallback, useEffect, useState } from "react";
import { getReference } from "./api.js";

// Mirror Component B's _normalize_name so payee↔entry lookups line up.
export const normName = (s) =>
  String(s || "").toLowerCase().replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();

// Org designators + structural signals. Broad on purpose: a false "entity" only
// risks showing a company name (fine); the safe default for anything person-shaped
// is to mask. Only consulted for names NOT found in the reference list.
const ORG = new RegExp(
  "\\b(l\\.?l\\.?c|inc|incorporated|corp|corporation|co|company|ltd|limited|l\\.?p|" +
  "l\\.?l\\.?p|pllc|plc|gmbh|s\\.?a|s\\.?r\\.?l|bv|bvba|fze|fz|group|holdings?|foundation|" +
  "trust|systems?|solutions?|services?|consult\\w*|construction|industr\\w*|technolog\\w*|" +
  "international|center|centre|associat\\w*|partners|enterprise\\w*|bank|fund|capital|" +
  "management|university|college|institute|laborator\\w*|labs?|hospital|clinic|medical|" +
  "pharmacy|supply|supplies|trading|energy|resources|logistics|manufacturing|motors|" +
  "electric|airlines?|railway|department|agency|bureau|administration|office|commission|" +
  "authority|district|county|regents|board|jewellery|refining|development|city|awards|" +
  "security|scientific|production|measuring)\\b", "i");

export function looksLikeEntity(name) {
  const n = String(name || "");
  if (!n.trim()) return true;                       // nothing to protect
  if (ORG.test(n)) return true;                     // has an org designator
  if (/[&,]/.test(n)) return true;                  // "CFK, INC" / "Teapot Oil & Refining"
  if (/\d/.test(n)) return true;                    // "LOLA LOLITA 1110 ..."
  // NB: no bare token-count rule — multi-part person names ("James O. Wilson Jr.")
  // must not be mistaken for orgs. Err toward masking when there is no org signal.
  return false;
}

const SUFFIX = /^(jr|sr|ii|iii|iv|v)\.?$/i;

// "James O. Wilson Jr." -> "James W."  ·  "ARNITA LEFF" -> "ARNITA L."
export function maskIndividualName(raw) {
  const name = String(raw || "").trim();
  if (!name) return name;
  const parts = name.split(/\s+/);
  const first = parts[0];
  let surname = null;
  for (let i = parts.length - 1; i >= 1; i--) {
    if (!SUFFIX.test(parts[i])) { surname = parts[i]; break; }
  }
  if (!surname) return first;                        // single token / mononym
  const m = surname.match(/[A-Za-zÀ-ɏ]/);  // first letter incl. accents
  return m ? `${first} ${m[0].toUpperCase()}.` : first;
}

// Decide masked/full. Precedence: explicit classification > reference map > heuristic.
function isIndividual(name, classification, map) {
  if (classification === "Individual") return true;
  if (classification === "Entity") return false;
  const key = normName(name);
  if (map && map.has(key)) return map.get(key) === "Individual"; // null seed -> not individual -> full
  return !looksLikeEntity(name);                    // unlisted -> conservative heuristic
}

export function maskName(name, classification, map) {
  if (name == null || name === "") return name;
  return isIndividual(name, classification, map) ? maskIndividualName(name) : name;
}

// Redact an individual payee's name inside model-generated brief prose: replace the
// full name and the standalone surname token, keeping the first name (matching the
// "First L." format). Advisory text, best-effort.
export function redactName(text, payeeName, classification, map) {
  if (!text || !payeeName || !isIndividual(payeeName, classification, map)) return text;
  const masked = maskIndividualName(payeeName);
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  let out = String(text).replace(new RegExp(esc(payeeName.trim()), "gi"), masked);
  const parts = payeeName.trim().split(/\s+/);
  for (let i = parts.length - 1; i >= 1; i--) {
    if (!SUFFIX.test(parts[i]) && parts[i].length >= 2) {
      const init = parts[i].match(/[A-Za-zÀ-ɏ]/);
      if (init) out = out.replace(new RegExp("\\b" + esc(parts[i]) + "\\b", "gi"), init[0].toUpperCase() + ".");
      break;
    }
  }
  return out;
}

// Reference classification map, loaded once and cached across surfaces.
let _mapPromise = null;
function loadMap() {
  if (!_mapPromise) {
    _mapPromise = getReference()
      .then((d) => {
        const m = new Map();
        for (const e of d.entries || []) if (e && e.name) m.set(normName(e.name), e.classification || null);
        return m;
      })
      .catch(() => new Map());
  }
  return _mapPromise;
}

// Hook: returns maskers backed by the reference map. Before the map resolves,
// explicit-classification calls work immediately and bare names fall back to the
// heuristic (still masks person-shaped names — fail safe).
export function useNameMasker() {
  const [map, setMap] = useState(null);
  useEffect(() => {
    let live = true;
    loadMap().then((m) => { if (live) setMap(m); });
    return () => { live = false; };
  }, []);
  return {
    mask: useCallback((name, classification) => maskName(name, classification, map), [map]),
    isIndividual: useCallback((name, classification) => isIndividual(name, classification, map), [map]),
    redact: useCallback((text, name, classification) => redactName(text, name, classification, map), [map]),
  };
}
