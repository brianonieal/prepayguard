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


def test_normalize_firm_record_maps_schema_and_drops_tin():
    ing = _load()
    e = ing.normalize_record({
        "entityName": "Bad Vendor LLC", "ueiSAM": "ABC123DEF456",
        "classificationType": "Firm", "exclusionType": "Prohibition/Restriction",
        "excludingAgencyName": "GSA", "recordStatus": "Active"})
    assert e["name"] == "Bad Vendor LLC"
    assert e["tin"] == "" and e["uei"] == "ABC123DEF456"
    assert e["source"] == "sam_exclusions" and e["severity"] == "high"
    assert e["classification"] == "Firm"


def test_normalize_individual_assembles_name_parts():
    ing = _load()
    e = ing.normalize_record({
        "firstName": "Jane", "middleName": "Q", "lastName": "Public",
        "classificationType": "Individual", "exclusionType": "Voluntary Exclusion",
        "recordStatus": "Active"})
    assert e["name"] == "Jane Q Public"
    assert e["severity"] == "medium"  # voluntary exclusion maps a step down
    assert e["classification"] == "Individual"


def test_inactive_and_nameless_records_are_dropped():
    ing = _load()
    assert ing.normalize_record({"entityName": "Terminated Co", "recordStatus": "Inactive"}) is None
    assert ing.normalize_record({"entityName": "", "recordStatus": "Active"}) is None
    # no status + a termination date -> inactive
    assert ing.normalize_record({"entityName": "Old Co", "terminationDate": "2020-01-01"}) is None
    # no status + no termination -> active
    assert ing.normalize_record({"entityName": "Live Co"})["name"] == "Live Co"


def test_unknown_exclusion_type_defaults_to_high():
    ing = _load()
    e = ing.normalize_record({"entityName": "Mystery Co", "exclusionType": "Something New", "recordStatus": "Active"})
    assert e["severity"] == "high"  # fail-safe: unknown -> treat as strong signal


def test_normalize_all_dedupes_on_name_and_uei():
    ing = _load()
    raw = [
        {"entityName": "Dup Co", "ueiSAM": "U1", "recordStatus": "Active"},
        {"entityName": "dup co", "ueiSAM": "U1", "recordStatus": "Active"},  # same name+uei -> dropped
        {"entityName": "Dup Co", "ueiSAM": "U2", "recordStatus": "Active"},  # same name, diff uei -> kept
        {"entityName": "Gone", "recordStatus": "Inactive"},                   # dropped
    ]
    out = ing.normalize_all(raw)
    assert len(out) == 2


def test_records_from_payload_tolerates_shapes():
    ing = _load()
    assert ing._records_from_payload({"excludedEntity": [{"a": 1}]}) == [{"a": 1}]
    assert ing._records_from_payload({"_embedded": {"results": [{"b": 2}]}}) == [{"b": 2}]
    assert ing._records_from_payload({"nothing": True}) == []


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
