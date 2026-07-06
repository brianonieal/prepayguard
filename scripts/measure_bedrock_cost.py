#!/usr/bin/env python3
"""Measure the real per-invocation Bedrock cost of the two LLM paths (Work Order 3).

Captures REAL token counts from live Bedrock (Titan embeddings for Component B's
semantic match; Nova Lite reviewer briefs from the console API), multiplies by the
current published us-east-2 on-demand rates, and prints the concrete cost line.

Rates below were confirmed via the AWS Price List API (ServiceCode AmazonBedrock,
us-east-2 / Ohio) on 2026-07-06 and are pinned here so the figure is reproducible;
re-confirm and update if AWS changes pricing (the doc records how).

Usage: python scripts/measure_bedrock_cost.py [--briefs N]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent

# AWS Price List API, ServiceCode=AmazonBedrock, us-east-2 (Ohio), confirmed 2026-07-06.
# usagetype USE2-TitanEmbeddingV2-Text-input-tokens / USE2-NovaLite-input-tokens / -output-tokens.
TITAN_V2_INPUT_PER_1K = 0.00002   # embeddings bill input tokens only
NOVA_LITE_INPUT_PER_1K = 0.00006
NOVA_LITE_OUTPUT_PER_1K = 0.00024

EMBED_MODEL = "amazon.titan-embed-text-v2:0"
BRIEF_MODEL = "amazon.nova-lite-v1:0"


def _load_console_api():
    spec = importlib.util.spec_from_file_location("console_api_app", ROOT / "src/console_api/app.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _rec(payee, source, sev, conf, score):
    return {"payment_id": "cost-measure", "payment": {"payee": payee, "amount": 25000},
            "decision": {"disposition": "review", "risk_score": score,
                         "reasons": [f"name_semantic match on {source} (severity {sev})"]},
            "evidence": {"matches": [{"source": source, "severity": sev, "matched_on": "name_semantic",
                                      "confidence": conf, "similarity": 0.86}]},
            "provenance": {"reference_list_version": 3}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--briefs", type=int, default=3)
    args = ap.parse_args()
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-2")
    br = boto3.client("bedrock-runtime", region_name="us-east-2")
    capp = _load_console_api()

    # 1) Embedding path: real input-token counts over the WO1 eval-set names.
    data = json.loads((ROOT / "scripts/semantic_eval_set.json").read_text(encoding="utf-8"))
    names = [e["name"] for e in data["reference_entries"]] + [c["payee"] for c in data["cases"]]
    embed_tokens = 0
    for n in names:
        r = br.invoke_model(modelId=EMBED_MODEL,
                            body=json.dumps({"inputText": n, "normalize": True}),
                            accept="application/json", contentType="application/json")
        embed_tokens += json.loads(r["body"].read()).get("inputTextTokenCount", 0)
    embed_cost = embed_tokens / 1000 * TITAN_V2_INPUT_PER_1K

    # 2) Brief path: real Nova Lite usage using the shipped BRIEF_SYSTEM prompt.
    records = ([_rec("Globex Overseas Incorporated", "oig_leie", "high", 86, 60),
                _rec("Acme Shell Limited Liability Company", "sam_exclusions", "high", 90, 60),
                _rec("Umbrella Holding Grp", "treasury_offset", "medium", 94, 56)] * 4)[:args.briefs]
    in_tok = out_tok = 0
    for record in records:
        facts = {"payment_id": record["payment_id"], "payee": record["payment"]["payee"],
                 "amount": record["payment"]["amount"], "disposition": record["decision"]["disposition"],
                 "risk_score": record["decision"]["risk_score"], "reasons": record["decision"]["reasons"],
                 "matches": record["evidence"]["matches"],
                 "reference_list_version": record["provenance"]["reference_list_version"]}
        resp = br.converse(modelId=BRIEF_MODEL, system=[{"text": capp.BRIEF_SYSTEM}],
                           messages=[{"role": "user", "content": [{"text":
                               "Screening record:\n" + json.dumps(facts, default=str) + "\n\nWrite the brief."}]}],
                           inferenceConfig={"maxTokens": 300, "temperature": 0.2})
        u = resp["usage"]
        in_tok += u["inputTokens"]
        out_tok += u["outputTokens"]
    brief_cost = in_tok / 1000 * NOVA_LITE_INPUT_PER_1K + out_tok / 1000 * NOVA_LITE_OUTPUT_PER_1K
    n = len(records)

    print(f"Semantic embeddings : {len(names)} calls, {embed_tokens} input tokens  = ${embed_cost:.7f}")
    print(f"                      (per embedding avg {embed_tokens/len(names):.1f} tok = ${embed_cost/len(names):.9f})")
    print(f"Adjudication briefs : {n} briefs, {in_tok} in / {out_tok} out tokens    = ${brief_cost:.7f}")
    print(f"                      (per brief avg {in_tok/n:.0f} in / {out_tok/n:.0f} out = ${brief_cost/n:.7f})")
    print(f"TOTAL measured run  : {len(names)} embeddings + {n} briefs               = ${embed_cost + brief_cost:.7f}")


if __name__ == "__main__":
    main()
