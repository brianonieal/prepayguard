"""C4 (V8: repo-reproducible). Does the 35-char cap open a false-accept path against the 11
over-35 reference entries? Three plausible <=35 forms per entity (truncation / distinctive tail /
abbreviation), screened against each entity's own vector (exact/fuzzy/semantic). Reproduces
`C4_long_entity_cap_matchability`. Run: python scripts/sweep_c4.py
"""
# ruff: noqa: E702  (compact evidence script; multiple statements per line by design)
from __future__ import annotations

import json
import re

from evasion_common import (
    FUZZY_THRESHOLD,
    SEM_THRESHOLD,
    cosine,
    embed,
    fuzzy,
    normalize_name,
    reference_vectors,
)

THR, FUZZY = SEM_THRESHOLD, FUZZY_THRESHOLD
ABBR = [("LIMITED LIABILITY COMPANY", "LLC"), ("LIMITED", "LTD"), ("CORPORATION", "CORP"),
        ("INCORPORATED", "INC"), ("COMPANY", "CO"), ("INTERNATIONAL", "INTL"), ("ASSOCIATION", "ASSN"),
        ("DEVELOPMENT", "DEV"), ("DEVELOPER", "DEV"), ("MECHANICAL", "MECH"), ("ENGINEERING", "ENG"),
        ("TECHNOLOGY", "TECH"), ("PRODUCTION", "PROD"), ("SCIENTIFIC", "SCI"), ("COMMUNITY", "COMM"),
        ("TRADING", "TRDG"), ("JEWELLERY", "JWLY"), ("SPECIALIZED", "SPEC"), (" AND ", " & ")]
# hand-picked distinctive tails / cores (<=35) a payer would plausibly submit
TAIL = {
    "LIMITED LIABILITY COMPANY SPECIALIZED DEVELOPER ALABUGA SOUTH PARK": "ALABUGA SOUTH PARK LLC",
    "SCIENTIFIC AND PRODUCTION ASSOCIATION OF MEASURING TECHNOLOGY": "MEASURING TECHNOLOGY ASSN",
    "TAWU BVBA MECHANICAL ENGINEERING AND TRADING COMPANY": "TAWU BVBA",
    "Citadel Community Development Corporation": "Citadel Community Dev Corp",
    "Usamah 'Abd-al-Wahid al-Jaza'iri BELKACEM": "Usamah al-Jaza'iri BELKACEM",
    "SUN SCIENCE INTERNATIONAL CO., LIMITED": "SUN SCIENCE INTL CO LTD",
    "GOLDEN LUXURY JEWELLERY TRADING L.L.C": "GOLDEN LUXURY JEWELLERY LLC",
    "AURORATOOLS LIMITED LIABILITY COMPANY": "AURORATOOLS LLC",
    "LOLA LOLITA 1110, S. DE R.L. DE C.V.": "LOLA LOLITA 1110 SA DE CV",
    "LIMITED LIABILITY COMPANY LITHIUMION": "LITHIUMION LLC",
    "LIMITED LIABILITY COMPANY OSNOVA LAB": "OSNOVA LAB LLC",
}


def abbrev(name):
    s = name
    for a, b in ABBR:
        s = re.sub(a, b, s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()[:35]


def screen(form, name, vec):
    ex = normalize_name(form) == normalize_name(name)
    fu = fuzzy(form, name)
    se = cosine(embed(form), vec)
    return {"form": form, "len": len(form), "exact": ex, "fuzzy": round(fu, 3),
            "semantic": round(se, 4), "matched": ex or fu >= FUZZY or se >= THR}


def main():
    stored = reference_vectors()
    over = [n for n in stored if len(n) > 35]
    out = {"threshold": THR, "fuzzy_threshold": FUZZY, "n_over_35": len(over), "entries": [], "unmatchable_count": 0}
    unmatchable = 0
    for name in sorted(over, key=lambda x: -len(x)):
        vec = stored[name]
        forms = {"truncate_35": name[:35], "distinctive_tail": TAIL[name], "abbreviation": abbrev(name)}
        rows = {k: screen(v, name, vec) for k, v in forms.items()}
        any_match = any(r["matched"] for r in rows.values())
        if not any_match:
            unmatchable += 1
        out["entries"].append({"name": name, "len": len(name), "any_form_matches": any_match, "forms": rows})
    out["unmatchable_count"] = unmatchable
    print(json.dumps({"n_over_35": len(over), "unmatchable_count": unmatchable}))
    return out


if __name__ == "__main__":
    main()
