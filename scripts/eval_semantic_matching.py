#!/usr/bin/env python3
"""Evaluate the Component B semantic-matching layer (Work Order 1, course objective 5).

Measures precision, recall, F1, and false-positive rate of the Bedrock-embedding
cosine matcher across a sweep of cosine thresholds around the deployed default
(SEMANTIC_THRESHOLD = 0.72), using the labeled set in scripts/semantic_eval_set.json.

The similarity and metric math live in pure functions (best_match, sweep) so the
CI test (tests/test_semantic_eval.py) exercises the exact same code with
deterministic synthetic vectors, while this script feeds those functions REAL
Titan embeddings. It reuses Component B's own _cosine so the eval measures the
shipped code path, not a re-implementation.

Framing (documented in docs/sme/SEMANTIC_EVAL.md): the semantic net runs only on
the residue the string rules cleared, and a hit is capped to REVIEW by Component
C. So a positive that is NOT flagged is a bad-payee variant that slips to approve
(a false ACCEPT, the costly error), and a negative that IS flagged is a clean
payment sent to a human (a false REJECT, wasted reviewer time only). Metrics use
the binary flag / no-flag decision:
  positive flagged            -> TP        positive not flagged -> FN (false accept)
  negative (hard/clean) flagged -> FP (false reject)   negative not flagged -> TN

Usage:
  python scripts/eval_semantic_matching.py                 # real Bedrock, full sweep
  python scripts/eval_semantic_matching.py --stability     # embed twice, prove determinism
  python scripts/eval_semantic_matching.py --json out.json # also write results JSON
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL_SET = ROOT / "scripts" / "semantic_eval_set.json"
DEFAULT_THRESHOLDS = [0.60, 0.64, 0.68, 0.70, 0.72, 0.74, 0.76, 0.80, 0.84, 0.88]
DEPLOYED_THRESHOLD = 0.72


def _load_component_b():
    """Import Component B by path (same trick as tests/conftest.py) to reuse its _cosine/_embed."""
    path = ROOT / "src" / "component_b_enrichment" / "app.py"
    spec = importlib.util.spec_from_file_location("component_b_enrichment_app", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---- pure logic (no Bedrock): shared by the script and the CI test ----------

def best_match(payee_vec, ref_vectors, cosine):
    """Return (best_ref_name, best_similarity) over the reference vectors, mirroring
    Component B._semantic_match (single best entry). ref_vectors: list of (name, vec)."""
    best_name, best_sim = None, -1.0
    for name, vec in ref_vectors:
        sim = cosine(payee_vec, vec)
        if sim > best_sim:
            best_name, best_sim = name, sim
    return best_name, best_sim


def sweep(scored_cases, thresholds):
    """scored_cases: list of dicts with label, target, best_name, best_sim.
    Returns a list of per-threshold metric rows."""
    rows = []
    for t in thresholds:
        tp = fn = fp = tn = target_hit = 0
        for c in scored_cases:
            flagged = c["best_sim"] >= t
            is_positive = c["label"] == "positive"
            if is_positive and flagged:
                tp += 1
                if c["best_name"] == c["target"]:
                    target_hit += 1
            elif is_positive and not flagged:
                fn += 1
            elif not is_positive and flagged:
                fp += 1
            else:
                tn += 1
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        fpr = fp / (fp + tn) if (fp + tn) else 0.0
        rows.append({
            "threshold": round(t, 4), "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4), "fpr": round(fpr, 4),
            "target_accuracy_on_flagged_positives": round(target_hit / tp, 4) if tp else None,
        })
    return rows


def score_cases(cases, payee_vectors, ref_vectors, cosine):
    """Attach best_name/best_sim to each case from precomputed vectors."""
    scored = []
    for c in cases:
        bn, bs = best_match(payee_vectors[c["payee"]], ref_vectors, cosine)
        scored.append({**c, "best_name": bn, "best_sim": round(bs, 4)})
    return scored


# ---- real-Bedrock driver ----------------------------------------------------

def _print_table(rows):
    hdr = f"{'thresh':>7} {'TP':>3} {'FN':>3} {'FP':>3} {'TN':>3} {'prec':>6} {'recall':>7} {'F1':>6} {'FPR':>6} {'tgt_acc':>8}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        star = "  <- deployed" if abs(r["threshold"] - DEPLOYED_THRESHOLD) < 1e-9 else ""
        ta = "" if r["target_accuracy_on_flagged_positives"] is None else f"{r['target_accuracy_on_flagged_positives']:.2f}"
        print(f"{r['threshold']:>7.2f} {r['tp']:>3} {r['fn']:>3} {r['fp']:>3} {r['tn']:>3} "
              f"{r['precision']:>6.3f} {r['recall']:>7.3f} {r['f1']:>6.3f} {r['fpr']:>6.3f} {ta:>8}{star}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stability", action="store_true", help="embed the set twice and report max vector drift")
    ap.add_argument("--json", metavar="PATH", help="write full results JSON to PATH")
    args = ap.parse_args()

    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-2")
    b = _load_component_b()
    data = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    ref_entries = data["reference_entries"]
    cases = data["cases"]

    # Real Titan embeddings for every reference name and every test payee.
    print(f"Embedding {len(ref_entries)} reference names and {len(cases)} test payees via "
          f"{os.environ.get('EMBED_MODEL', 'amazon.titan-embed-text-v2:0')} ...")
    ref_vectors = [(e["name"], b._embed(e["name"])) for e in ref_entries]
    payee_vectors = {c["payee"]: b._embed(c["payee"]) for c in cases}

    if args.stability:
        ref2 = {e["name"]: b._embed(e["name"]) for e in ref_entries}
        payee2 = {c["payee"]: b._embed(c["payee"]) for c in cases}
        max_drift = 0.0
        for name, vec in ref_vectors:
            max_drift = max(max_drift, max(abs(a - z) for a, z in zip(vec, ref2[name], strict=True)))
        for payee, vec in payee_vectors.items():
            max_drift = max(max_drift, max(abs(a - z) for a, z in zip(vec, payee2[payee], strict=True)))
        print(f"STABILITY: max abs per-dimension drift across two independent embed passes = {max_drift:.2e}")

    scored = score_cases(cases, payee_vectors, ref_vectors, b._cosine)
    rows = sweep(scored, DEFAULT_THRESHOLDS)

    print("\nPer-case best match (payee -> best reference entity @ cosine):")
    for c in sorted(scored, key=lambda x: (x["label"], -x["best_sim"])):
        tgt = f"  target={c.get('target')}" if c["label"] == "positive" else ""
        print(f"  [{c['label']:>13}] {c['payee']:<38} -> {c['best_name']:<24} {c['best_sim']:.3f}{tgt}")

    print("\nThreshold sweep:")
    _print_table(rows)

    if args.json:
        Path(args.json).write_text(json.dumps({
            "eval_set": str(EVAL_SET.relative_to(ROOT)),
            "embed_model": os.environ.get("EMBED_MODEL", "amazon.titan-embed-text-v2:0"),
            "deployed_threshold": DEPLOYED_THRESHOLD,
            "n_positive": sum(1 for c in cases if c["label"] == "positive"),
            "n_hard_negative": sum(1 for c in cases if c["label"] == "hard_negative"),
            "n_clean": sum(1 for c in cases if c["label"] == "clean"),
            "per_case": scored, "sweep": rows,
        }, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json}")


if __name__ == "__main__":
    main()
