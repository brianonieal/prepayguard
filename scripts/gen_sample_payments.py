#!/usr/bin/env python3
"""Generate legit-looking synthetic payment batches for testing PrePayGuard.

Reads the SAME synthetic Do Not Pay reference list the pipeline screens against
(src/component_b_enrichment/reference_data.json), so the flagged rows actually
trigger real dispositions instead of all clearing:

  - clean payee, unmatched TIN              -> approve
  - exact reference NAME (clean TIN)        -> review  (name match, capped below reject)
  - reference TIN on a HIGH-severity entry  -> reject  (strong identity hit; e.g. a
                                                        renamed shell reusing a debarred EIN)
  - reference TIN on a MEDIUM-severity entry-> review
  - a 1-char fuzzy variant of a ref name    -> review  (>= 0.90 similarity, the app threshold)

Everything is fabricated. Clean-row TINs avoid the reserved 90000000x range so
they never collide with the reference list. `_expected` is a guide; the real
disposition is whatever the live pipeline decides.

Usage:
  python scripts/gen_sample_payments.py                         # 25 rows to stdout
  python scripts/gen_sample_payments.py 40                      # 40 rows to stdout
  python scripts/gen_sample_payments.py 30 out.csv             # 30 rows to a file
"""
import csv
import difflib
import json
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = json.loads((ROOT / "src/component_b_enrichment/reference_data.json").read_text(encoding="utf-8"))
ENTRIES = REF["entries"]
HIGH = [e for e in ENTRIES if e["severity"] == "high"]
MED = [e for e in ENTRIES if e["severity"] == "medium"]

CLEAN_VENDORS = [
    "Meridian Office Supplies LLC", "Cascade Freight Solutions Inc",
    "BlueRiver Analytics Group", "Summit Facilities Management",
    "Harborview Medical Associates", "Pinnacle IT Consulting LLC",
    "Evergreen Landscaping Co", "Northgate Construction Partners",
    "Lakeside Catering Services", "Delphi Software Labs Inc",
    "Copperfield Legal Group LLP", "Sunbelt Logistics Corp",
    "Ironwood Security Services", "Riverbend Staffing Agency",
    "Granite Peak Engineering", "Fairwind Travel Management",
    "Oakmont Printing Solutions", "Silverline Telecom Inc",
    "Redwood Environmental Svcs", "Beacon Data Systems LLC",
    "Tidewater Marine Supply", "Highland Dairy Distributors",
    "Crossroads Fleet Services", "Vanguard Cleaning Co",
    "Maplewood Pharmaceuticals", "Stonegate Property Mgmt",
    "Aurora Electrical Contractors", "Brightpath Education Group",
    "Cardinal Freight Brokers", "Willowmere Consulting Group",
]


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", str(s).lower())).strip()


def clean_tin():
    while True:
        t = f"{random.randint(10, 89):02d}-{random.randint(1000000, 9999999):07d}"
        if not re.sub(r"\D", "", t).startswith("90000000"):
            return t


def money():
    return f"{random.randint(200, 84000)}.{random.randint(0, 99):02d}"


def fuzzy_variant(name):
    # Drop one interior letter; keep only if still >= 0.90 similar (app threshold).
    idxs = [i for i, c in enumerate(name) if c.isalpha()]
    random.shuffle(idxs)
    for i in idxs:
        cand = name[:i] + name[i + 1:]
        if difflib.SequenceMatcher(None, norm(cand), norm(name)).ratio() >= 0.90:
            return cand
    return name  # short name: falls back to an exact match (still routes to review)


def build(n):
    n_reject = max(2, n // 8)
    n_review_name = max(2, n // 8)
    n_review_tin_med = max(1, n // 12) if MED else 0
    n_fuzzy = max(1, n // 12)
    n_clean = max(0, n - n_reject - n_review_name - n_review_tin_med - n_fuzzy)

    staged = []
    for _ in range(n_clean):
        staged.append((random.choice(CLEAN_VENDORS), clean_tin(), "approve"))
    for _ in range(n_reject):
        e = random.choice(HIGH)  # renamed shell reusing a debarred/deceased TIN
        staged.append((random.choice(CLEAN_VENDORS), e["tin"], "reject"))
    for _ in range(n_review_name):
        e = random.choice(ENTRIES)  # exact Do Not Pay name, clean TIN
        staged.append((e["name"], clean_tin(), "review"))
    for _ in range(n_review_tin_med):
        e = random.choice(MED)
        staged.append((random.choice(CLEAN_VENDORS), e["tin"], "review"))
    for _ in range(n_fuzzy):
        e = random.choice(ENTRIES)  # near-miss spelling of a listed name
        staged.append((fuzzy_variant(e["name"]), "", "review"))

    random.shuffle(staged)
    seed = int(time.time()) % 100000
    rows = []
    for i, (payee, tin, expected) in enumerate(staged, 1):
        rows.append({
            "payment_id": f"INV-2026-{seed:05d}-{i:03d}",
            "payee": payee, "payee_tin": tin, "amount": money(), "_expected": expected,
        })
    return rows


def main():
    args = sys.argv[1:]
    n = next((int(a) for a in args if a.isdigit()), 25)
    out_path = next((a for a in args if not a.isdigit()), None)
    rows = build(n)

    fh = open(out_path, "w", newline="", encoding="utf-8") if out_path else sys.stdout
    writer = csv.writer(fh)
    writer.writerow(["payment_id", "payee", "payee_tin", "amount"])
    for r in rows:
        writer.writerow([r["payment_id"], r["payee"], r["payee_tin"], r["amount"]])
    if out_path:
        fh.close()

    c = Counter(r["_expected"] for r in rows)
    sys.stderr.write(
        f"generated {len(rows)} rows -> {out_path or 'stdout'}: "
        f"{c.get('approve', 0)} approve, {c.get('review', 0)} review, {c.get('reject', 0)} reject\n"
    )


if __name__ == "__main__":
    main()
