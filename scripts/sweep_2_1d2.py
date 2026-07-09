"""2.1d(d) concrete residual (V8: repo-reproducible). Of the 96 v4 entries, how many EVADE via a
fitting short append under a 35 / 22-char cap. Reproduces `2_1d_residual_N_of_96` in
docs/evidence/matcher_evasion_bounded_data.json. Run: python scripts/sweep_2_1d2.py
"""
from __future__ import annotations

import json

from evasion_common import SEM_THRESHOLD, cosine, embed, fuzzy, reference_vectors

THR = SEM_THRESHOLD
TOKENS = [("OK PAY", 6), ("FY26Q3", 6), ("ZX QQ", 5), ("PO 7781", 7), ("JAZZ OWL", 8)]


def evadable_count(entries, cap):
    n_room = n_evade = 0
    evaders = []
    for name, vr in entries.items():
        budget = cap - len(name) - 1
        fits = [(t, ln) for t, ln in TOKENS if ln <= budget]
        if not fits:
            continue
        n_room += 1
        for t, _ in fits:
            p = f"{name} {t}"
            if cosine(embed(p), vr) < THR and fuzzy(p, name) < 0.90:
                n_evade += 1
                if len(evaders) < 8:
                    evaders.append(name)
                break
    return {"cap": cap, "total": len(entries), "have_room": n_room, "confirmed_evade": n_evade,
            "pct_evade": round(100 * n_evade / len(entries), 1), "sample_evaders": evaders}


def main():
    entries = reference_vectors()
    out = {"threshold": THR, "tokens_tried": [t for t, _ in TOKENS],
           "cap_35": evadable_count(entries, 35), "cap_22": evadable_count(entries, 22)}
    print(json.dumps({"cap_35": out["cap_35"]["confirmed_evade"], "cap_22": out["cap_22"]["confirmed_evade"],
                      "total": out["cap_35"]["total"]}))
    return out


if __name__ == "__main__":
    main()
