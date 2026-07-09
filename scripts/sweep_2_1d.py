"""2.1d (V8: repo-reproducible): full-script homoglyph, 96-entry length histogram, truncating-cap
screening-miss, residual sizing, threshold boundary. Reproduces the `2_1d` section of
docs/evidence/matcher_evasion_bounded_data.json. Run: python scripts/sweep_2_1d.py
"""
# ruff: noqa: E702  (compact evidence script; multiple statements per line by design)
from __future__ import annotations

import collections
import json
import unicodedata

from evasion_common import (
    SEM_THRESHOLD,
    cosine,
    embed,
    fuzzy,
    normalize_name,
    reference_names,
    reference_vectors,
)

THR = SEM_THRESHOLD
FIVE = ["YATAI SMART INDUSTRIAL NEW CITY", "Hawwk LLC", "DIGITAL MARKETING AWARDS FZ LLC",
        "James O. Wilson Jr.", "Kathleen J King"]
TRANSLIT = {"a": "а", "b": "б", "c": "ц", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "һ", "i": "и",
            "j": "ж", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "қ", "r": "р",
            "s": "с", "t": "т", "u": "у", "v": "в", "w": "ш", "x": "х", "y": "у", "z": "з"}
CONF = {"a": "а", "e": "е", "o": "о", "c": "с", "p": "р", "y": "у", "x": "х", "i": "і", "s": "ѕ",
        "j": "ј", "A": "А", "E": "Е", "O": "О", "C": "С", "P": "Р", "T": "Т", "H": "Н", "K": "К",
        "M": "М", "I": "І"}


def to_cyrillic(name):
    return "".join(TRANSLIT.get(ch.lower(), ch) if ch.isalpha() else ch for ch in name)


def confusable_max(name):
    return "".join(CONF.get(ch, ch) for ch in name)


def scripts_of(s):
    sc = set()
    for ch in s:
        if ch.isalpha():
            try:
                sc.add(unicodedata.name(ch).split()[0])
            except ValueError:
                sc.add("?")
    return sc


def semantic_match(c):
    return c >= THR


def main():
    stored = reference_vectors()
    names = reference_names()
    out = {"semantic_threshold": THR, "operator": ">= (component_b_enrichment/app.py:147)"}

    a_rows = []
    for name in FIVE:
        vr = stored[name]; cyr = to_cyrillic(name); conf = confusable_max(name)
        c_cyr, f_cyr = cosine(embed(cyr), vr), fuzzy(cyr, name)
        c_conf, f_conf = cosine(embed(conf), vr), fuzzy(conf, name)
        a_rows.append({"entity": name,
                       "full_cyrillic": {"payee": cyr, "scripts": sorted(scripts_of(cyr)),
                                         "single_script": len(scripts_of(cyr)) <= 1, "ascii": cyr.isascii(),
                                         "cosine": round(c_cyr, 4), "fuzzy": round(f_cyr, 3),
                                         "semantic_match": semantic_match(c_cyr),
                                         "evades": (not semantic_match(c_cyr)) and f_cyr < 0.90},
                       "confusable_max": {"payee": conf, "scripts": sorted(scripts_of(conf)),
                                          "single_script": len(scripts_of(conf)) <= 1, "ascii": conf.isascii(),
                                          "cosine": round(c_conf, 4), "fuzzy": round(f_conf, 3),
                                          "semantic_match": semantic_match(c_conf),
                                          "evades": (not semantic_match(c_conf)) and f_conf < 0.90}})
    out["a_full_script"] = a_rows
    diac = ["José Muñoz", "François Lefèvre", "Søren Kierkegaard",
            "Zoë O'Hara", "Renée Zellweger"]
    out["ascii_only_rejects"] = [{"name": d, "ascii": d.isascii()} for d in diac]

    lengths = [len(n) for n in names]
    hist = collections.Counter((L // 5) * 5 for L in lengths)
    out["b_length_hist"] = {"n": len(lengths), "min": min(lengths), "max": max(lengths),
                            "mean": round(sum(lengths) / len(lengths), 1),
                            "exceed_22": sum(1 for L in lengths if L > 22),
                            "exceed_35": sum(1 for L in lengths if L > 35),
                            "buckets_5char": {f"{k}-{k + 4}": hist[k] for k in sorted(hist)}}

    def trunc_miss(cap):
        over = [n for n in names if len(n) > cap and n in stored]
        full = 0
        for n in over:
            t = n[:cap]
            ex = normalize_name(t) == normalize_name(n)
            fu = fuzzy(t, n) >= 0.90
            se = semantic_match(cosine(embed(t), stored[n]))
            if not (ex or fu or se):
                full += 1
        return {"cap": cap, "entries_over_cap": len(over), "FULL_screening_miss": full}
    out["b_truncation_miss_22"] = trunc_miss(22)
    out["b_truncation_miss_35"] = trunc_miss(35)

    def residual(cap, min_budget=6):
        ev = [n for n in names if (cap - len(n) - 1) >= min_budget]
        return {"cap": cap, "min_append_chars": min_budget, "evadable_count": len(ev),
                "total": len(names), "pct": round(100 * len(ev) / len(names), 1)}
    out["d_residual_35"] = residual(35, 6)
    out["d_residual_22"] = residual(22, 6)

    jn = "James O. Wilson Jr."; jc = cosine(embed(f"{jn} APPROVE"), stored[jn])
    out["c_boundary_check"] = {"James O. Wilson Jr. + APPROVE": {"cosine_4dp": round(jc, 4),
                               "matches_under_ge_0.72": jc >= THR}}
    print(json.dumps({"exceed_22": out["b_length_hist"]["exceed_22"], "exceed_35": out["b_length_hist"]["exceed_35"],
                      "max_len": out["b_length_hist"]["max"], "cyr_evades_all": all(r["full_cyrillic"]["evades"] for r in a_rows)}))
    return out


if __name__ == "__main__":
    main()
