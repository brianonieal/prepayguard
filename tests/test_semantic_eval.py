"""Reproducibility test for the semantic-matching evaluation (Work Order 1).

The accuracy NUMBERS in docs/sme/SEMANTIC_EVAL.md come from real Titan embeddings
(scripts/eval_semantic_matching.py, run against live Bedrock). This test does NOT
call Bedrock; it pins the pure metric + matching logic those numbers are computed
with, using deterministic synthetic vectors, so CI proves the sweep math is
correct without any Bedrock cost. If the metric code drifts, this fails.
"""
import importlib.util
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_eval():
    path = ROOT / "scripts" / "eval_semantic_matching.py"
    spec = importlib.util.spec_from_file_location("eval_semantic_matching", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cosine(u, v):
    dot = sum(a * b for a, b in zip(u, v, strict=True))
    nu = math.sqrt(sum(a * a for a in u)) or 1.0
    nv = math.sqrt(sum(b * b for b in v)) or 1.0
    return dot / (nu * nv)


def test_best_match_picks_single_highest_cosine():
    ev = _load_eval()
    ref = [("A", [1.0, 0.0]), ("B", [0.0, 1.0]), ("C", [0.7, 0.7])]
    name, sim = ev.best_match([1.0, 0.05], ref, _cosine)
    assert name == "A"
    assert sim > 0.9


def test_sweep_confusion_matrix_and_metrics_are_correct():
    ev = _load_eval()
    # Hand-built scored cases with known best_sim so the confusion matrix is exact.
    scored = [
        # positives (target matched)
        {"label": "positive", "target": "X", "best_name": "X", "best_sim": 0.90},
        {"label": "positive", "target": "Y", "best_name": "Y", "best_sim": 0.75},
        {"label": "positive", "target": "Z", "best_name": "Z", "best_sim": 0.60},  # below 0.72 -> FN
        # negatives
        {"label": "hard_negative", "best_name": "X", "best_sim": 0.80},  # >=0.72 -> FP
        {"label": "clean", "best_name": "Y", "best_sim": 0.20},          # TN
        {"label": "clean", "best_name": "Z", "best_sim": 0.10},          # TN
    ]
    rows = {r["threshold"]: r for r in ev.sweep(scored, [0.72])}
    r = rows[0.72]
    assert (r["tp"], r["fn"], r["fp"], r["tn"]) == (2, 1, 1, 2)
    assert r["precision"] == round(2 / 3, 4)
    assert r["recall"] == round(2 / 3, 4)
    assert r["fpr"] == round(1 / 3, 4)
    assert r["f1"] == round(2 * (2 / 3) * (2 / 3) / ((2 / 3) + (2 / 3)), 4)
    assert r["target_accuracy_on_flagged_positives"] == 1.0  # both flagged positives hit their target


def test_sweep_counts_wrong_target_positive_as_target_miss_not_recall_miss():
    ev = _load_eval()
    scored = [
        {"label": "positive", "target": "X", "best_name": "W", "best_sim": 0.90},  # flagged, wrong entity
        {"label": "positive", "target": "Y", "best_name": "Y", "best_sim": 0.90},  # flagged, right entity
    ]
    r = ev.sweep(scored, [0.72])[0]
    assert r["tp"] == 2 and r["recall"] == 1.0            # both flagged -> recall counts them
    assert r["target_accuracy_on_flagged_positives"] == 0.5  # only one pointed at the right entity


def test_higher_threshold_never_increases_recall():
    ev = _load_eval()
    scored = [
        {"label": "positive", "target": "X", "best_name": "X", "best_sim": 0.70},
        {"label": "positive", "target": "Y", "best_name": "Y", "best_sim": 0.85},
    ]
    rows = ev.sweep(scored, [0.60, 0.72, 0.80])
    recalls = [r["recall"] for r in rows]
    assert recalls == sorted(recalls, reverse=True)  # monotonically non-increasing in threshold


def test_eval_set_is_well_formed():
    ev = _load_eval()
    import json
    data = json.loads(ev.EVAL_SET.read_text(encoding="utf-8"))
    labels = {c["label"] for c in data["cases"]}
    assert labels == {"positive", "hard_negative", "clean"}
    # every positive names a target that exists in the reference list
    ref_names = {e["name"] for e in data["reference_entries"]}
    for c in data["cases"]:
        if c["label"] == "positive":
            assert c["target"] in ref_names, c["payee"]
