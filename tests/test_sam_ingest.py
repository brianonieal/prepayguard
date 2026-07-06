"""Deterministic tests for the real SAM.gov ingestion (Work Order 2).

No network and no Bedrock: pins the messy-data normalization, dedupe, severity
mapping, and the versioned-doc build (synthetic restricted sources preserved with
their embeddings, real SAM entries embedded) that the live publish depends on.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    path = ROOT / "scripts" / "ingest_sam_exclusions.py"
    spec = importlib.util.spec_from_file_location("ingest_sam_exclusions", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _sam(name=None, uei=None, classification="Firm", exclusion_type="Prohibition/Restriction",
         agency="GSA", status="Active", parts=None):
    """Build a record in the REAL nested SAM v4 shape (verified against the live API)."""
    ident = {"ueiSAM": uei, "entityName": name}
    if parts:
        ident.update(parts)  # prefix/firstName/middleName/lastName/suffix, entityName None
    return {
        "exclusionDetails": {"classificationType": classification, "exclusionType": exclusion_type,
                             "excludingAgencyName": agency},
        "exclusionIdentification": ident,
        "exclusionActions": {"listOfActions": [{"recordStatus": status, "terminationDate": "03-31-2227"}]},
    }


def test_normalize_firm_record_maps_schema_and_drops_tin():
    ing = _load()
    e = ing.normalize_record(_sam(name="Bad Vendor LLC", uei="ABC123DEF456",
                                  classification="Firm", exclusion_type="Prohibition/Restriction"))
    assert e["name"] == "Bad Vendor LLC"
    assert e["tin"] == "" and e["uei"] == "ABC123DEF456"
    assert e["source"] == "sam_exclusions" and e["severity"] == "high"
    assert e["classification"] == "Firm"


def test_normalize_individual_assembles_name_parts():
    ing = _load()
    e = ing.normalize_record(_sam(name=None, classification="Individual",
                                  exclusion_type="Voluntary Exclusion",
                                  parts={"firstName": "Jane", "middleName": "Q", "lastName": "Public"}))
    assert e["name"] == "Jane Q Public"
    assert e["severity"] == "medium"  # voluntary exclusion maps a step down
    assert e["classification"] == "Individual"


def test_completed_proceedings_maps_high():
    ing = _load()
    e = ing.normalize_record(_sam(name="Debarred Co", exclusion_type="Ineligible (Proceedings Complete)"))
    assert e["severity"] == "high"


def test_inactive_and_nameless_records_are_dropped():
    ing = _load()
    assert ing.normalize_record(_sam(name="Terminated Co", status="Inactive")) is None
    assert ing.normalize_record(_sam(name="", status="Active")) is None
    # no actions at all -> cannot confirm active -> dropped (conservative)
    assert ing.normalize_record({"exclusionIdentification": {"entityName": "Orphan Co"}}) is None


def test_unknown_exclusion_type_defaults_to_high():
    ing = _load()
    e = ing.normalize_record(_sam(name="Mystery Co", exclusion_type="Something New"))
    assert e["severity"] == "high"  # fail-safe: unknown -> treat as strong signal


def test_normalize_all_dedupes_on_name_and_uei():
    ing = _load()
    raw = [
        _sam(name="Dup Co", uei="U1"),
        _sam(name="dup co", uei="U1"),   # same name+uei -> dropped
        _sam(name="Dup Co", uei="U2"),   # same name, diff uei -> kept
        _sam(name="Gone", status="Inactive"),  # dropped
    ]
    out = ing.normalize_all(raw)
    assert len(out) == 2


def test_records_from_payload_tolerates_shapes():
    ing = _load()
    assert ing._records_from_payload({"excludedEntity": [{"a": 1}]}) == [{"a": 1}]
    assert ing._records_from_payload({"_embedded": {"results": [{"b": 2}]}}) == [{"b": 2}]
    assert ing._records_from_payload({"nothing": True}) == []


def test_extract_returns_records_directly(monkeypatch):
    ing = _load()
    monkeypatch.setattr(ing, "_get_json",
                        lambda url, timeout=60: {"excludedEntity": [_sam(name="A"), _sam(name="B"), _sam(name="C")]})
    raw = ing.fetch_exclusions_extract("k", ing.DEFAULT_ENDPOINT, limit=2)
    assert len(raw) == 2  # capped


def test_extract_polls_download_when_token_returned(monkeypatch):
    ing = _load()
    calls = {"n": 0}

    def fake(url, timeout=60):
        calls["n"] += 1
        return {"token": "T"} if calls["n"] == 1 else {"excludedEntity": [_sam(name="X")]}
    monkeypatch.setattr(ing, "_get_json", fake)
    raw = ing.fetch_exclusions_extract("k", ing.DEFAULT_ENDPOINT, limit=10)
    assert len(raw) == 1 and calls["n"] == 2  # generation call, then download call


def test_paginated_fetch_propagates_rate_limit(monkeypatch):
    import pytest
    ing = _load()

    def boom(url, timeout=60):
        raise ing.RateLimited("429 Too Many Requests")
    monkeypatch.setattr(ing, "_get_json", boom)
    with pytest.raises(ing.RateLimited):
        ing.fetch_exclusions("k", ing.DEFAULT_ENDPOINT, limit=10)


def test_build_doc_preserves_synthetic_replaces_sam_and_versions():
    ing = _load()
    current = {
        "version": 3, "semantic_threshold": 0.72,
        "sources": {"death_master_file": "DMF", "sam_exclusions": "synthetic"},
        "entries": [
            {"name": "John Q Public", "tin": "900000001", "source": "death_master_file",
             "severity": "high", "embedding": [0.1, 0.2], "embedding_model": "amazon.titan-embed-text-v2:0"},
            {"name": "Acme Shell LLC", "tin": "900000002", "source": "sam_exclusions", "severity": "high",
             "embedding": [0.3, 0.4]},  # synthetic SAM entry -> must be dropped
        ],
    }
    real = [{"name": "Real Bad Vendor LLC", "tin": "", "uei": "U9", "source": "sam_exclusions", "severity": "high"}]
    calls = []
    doc = ing.build_reference_doc(current, real, lambda name: calls.append(name) or [9.9, 9.9])

    assert doc["version"] == 4
    names = {e["name"] for e in doc["entries"]}
    assert "John Q Public" in names            # synthetic non-SAM preserved
    assert "Acme Shell LLC" not in names       # synthetic SAM replaced
    assert "Real Bad Vendor LLC" in names      # real SAM added
    # the preserved synthetic entry kept its ORIGINAL embedding (not re-embedded)
    dmf = next(e for e in doc["entries"] if e["name"] == "John Q Public")
    assert dmf["embedding"] == [0.1, 0.2]
    assert calls == ["Real Bad Vendor LLC"]    # only the real entry was embedded
    assert doc["semantic_threshold"] == 0.72
