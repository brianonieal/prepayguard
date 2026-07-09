"""Shared helpers for the matcher-evasion sweeps (V8 — makes them repo-reproducible).

The sweeps cosine payee embeddings against each reference entry's vector. Component G stores
`embedding = _embed(entry["name"])` and Titan v2 (`normalize:true`) is deterministic (0.00 drift,
EVAL_REPORT.md), so re-embedding the committed reference NAMES reproduces the exact stored vectors
— no dependency on the ephemeral S3 list. Reference names come from the committed V3 snapshot
`docs/evidence/reference_list_v4_snapshot.json`. Requires AWS creds with Bedrock (us-east-2).

Faithful to `src/component_b_enrichment/app.py`: `_embed` (Titan, normalize:true), `_cosine`,
`_normalize_name` (:89-91), fuzzy = difflib on the normalized strings (:171), semantic op `>=`
0.72 (:147), fuzzy threshold 0.90 (:45).
"""
from __future__ import annotations

import difflib
import hashlib
import json
import math
import os
import re
from pathlib import Path

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-2")
MODEL = "amazon.titan-embed-text-v2:0"
SEM_THRESHOLD = 0.72
FUZZY_THRESHOLD = 0.90
_REPO = Path(__file__).resolve().parent.parent
SNAPSHOT = _REPO / "docs" / "evidence" / "reference_list_v4_snapshot.json"
# Embedding cache (NOT committed) so repeated runs are cheap and offline-after-first.
_CACHE_PATH = Path(os.environ.get("EVASION_EMBED_CACHE",
                                  Path(os.environ.get("TEMP", "/tmp")) / "evasion_embed_cache.json"))
_cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8")) if _CACHE_PATH.exists() else {}
_bedrock = None


def _client():
    global _bedrock
    if _bedrock is None:
        _bedrock = boto3.client("bedrock-runtime", region_name=REGION)
    return _bedrock


def embed(text: str) -> list[float]:
    key = hashlib.sha256((MODEL + "|" + str(text or "")).encode("utf-8")).hexdigest()
    if key in _cache:
        return _cache[key]
    resp = _client().invoke_model(
        modelId=MODEL,
        body=json.dumps({"inputText": str(text or ""), "normalize": True}),
        accept="application/json", contentType="application/json",
    )
    vec = json.loads(resp["body"].read())["embedding"]
    _cache[key] = vec
    _CACHE_PATH.write_text(json.dumps(_cache), encoding="utf-8")
    return vec


def cosine(u, v) -> float:
    if not u or not v or len(u) != len(v):
        return 0.0
    dot = sum(a * b for a, b in zip(u, v, strict=True))  # lengths guarded equal above
    nu = math.sqrt(sum(a * a for a in u)) or 1.0
    nv = math.sqrt(sum(b * b for b in v)) or 1.0
    return dot / (nu * nv)


def normalize_name(name) -> str:
    n = re.sub(r"[^a-z0-9\s]", " ", str(name or "").lower())
    return re.sub(r"\s+", " ", n).strip()


def fuzzy(a, b) -> float:
    return difflib.SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


def reference_names() -> list[str]:
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return [e["name"] for e in snap["entries"]]


def reference_vectors() -> dict[str, list[float]]:
    """{name: embed(name)} — reproduces the stored v4 vectors (deterministic)."""
    return {name: embed(name) for name in reference_names()}
