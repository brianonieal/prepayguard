"""Deterministic tests for the real HHS-OIG LEIE ingestion (DEC-30).

No network and no Bedrock: pins the classification-from-source-columns rule (the PII
gate), the messy-data normalization ("NULL" tokens, NPI preservation, active filter),
dedupe, the deliberate individual/entity sample, and the versioned-doc build (other
sources preserved with their embeddings, real LEIE embedded). Mirrors test_sam_ingest.py.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    path = ROOT / "scripts" / "ingest_leie.py"
    spec = importlib.util.spec_from_file_location("ingest_leie", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _row(lastname="", firstname="", midname="", busname="", npi="0000000000",
         excltype="1128a1", reindate="00000000"):
    """A raw LEIE CSV row (the real UPDATED.csv column names)."""
    return {"LASTNAME": lastname, "FIRSTNAME": firstname, "MIDNAME": midname, "BUSNAME": busname,
            "NPI": npi, "EXCLTYPE": excltype, "REINDATE": reindate}


def test_individual_row_classifies_individual_and_assembles_name():
    ing = _load()
    e = ing.normalize_row(_row(lastname="AAKER", firstname="DEBHANNA"))
    assert e["classification"] == "Individual"      # PII gate: masked on the console
    assert e["name"] == "DEBHANNA AAKER"
    assert e["source"] == "oig_leie" and e["severity"] == "high"
    assert e["tin"] == ""                            # honest: no fabricated TIN -> review only (F6)


def test_entity_row_classifies_entity_and_uses_busname():
    ing = _load()
    e = ing.normalize_row(_row(busname="1 BEST CARE, INC"))
    assert e["classification"] == "Entity"           # shown full on the console
    assert e["name"] == "1 BEST CARE, INC"
    assert e["severity"] == "high"


def test_null_tokens_are_treated_as_missing():
    ing = _load()
    # real messiness: LASTNAME literal "NULL" -> dropped from the assembled name
    e = ing.normalize_row(_row(lastname="NULL", firstname="ANGELA", midname="JOHNSON"))
    assert e["classification"] == "Individual"
    assert e["name"] == "ANGELA JOHNSON"


def test_npi_preserved_and_placeholder_dropped():
    ing = _load()
    real = ing.normalize_row(_row(busname="101 FIRST CARE PHARMACY INC", npi="1972902351"))
    assert real["npi"] == "1972902351"               # preserved for provenance / future matching (F8)
    none = ing.normalize_row(_row(lastname="DOE", firstname="JANE", npi="0000000000"))
    assert none["npi"] is None and none["tin"] == "" # placeholder NPI dropped; TIN never fabricated


def test_reinstated_and_nameless_rows_are_dropped():
    ing = _load()
    assert ing.normalize_row(_row(lastname="GONE", firstname="JOE", reindate="20200101")) is None  # reinstated
    assert ing.normalize_row(_row()) is None          # no name at all


def test_normalize_all_dedupes_on_name_and_npi():
    ing = _load()
    raw = [
        _row(lastname="Dup", firstname="A", npi="1111111111"),
        _row(lastname="dup", firstname="a", npi="1111111111"),   # same name+npi -> dropped
        _row(lastname="Dup", firstname="A", npi="2222222222"),   # same name, diff npi -> kept
        _row(lastname="Gone", firstname="B", reindate="20200101"),  # reinstated -> dropped
    ]
    out = ing.normalize_all(raw)
    assert len(out) == 2


def test_deliberate_sample_mixes_both_classes_and_caps():
    ing = _load()
    entries = ([{"classification": "Individual", "name": f"P{i}"} for i in range(1000)]
               + [{"classification": "Entity", "name": f"E{i}"} for i in range(200)])
    out = ing.deliberate_sample(entries, total=120, entity_target=20)
    assert len(out) == 120
    classes = {e["classification"] for e in out}
    assert classes == {"Individual", "Entity"}       # both represented, not just file order
    assert sum(1 for e in out if e["classification"] == "Entity") == 20


def test_build_doc_preserves_others_replaces_leie_and_versions():
    ing = _load()
    current = {
        "version": 4, "semantic_threshold": 0.72,
        "sources": {"oig_leie": "synthetic", "sam_exclusions": "real"},
        "entries": [
            {"name": "Real SAM Vendor LLC", "tin": "", "uei": "U9", "source": "sam_exclusions",
             "severity": "high", "embedding": [0.5, 0.6], "embedding_model": "amazon.titan-embed-text-v2:0"},
            {"name": "John Q Public", "tin": "900000001", "source": "death_master_file",
             "severity": "high", "embedding": [0.1, 0.2]},
            {"name": "Globex Offshore Inc", "tin": "900000004", "source": "oig_leie",
             "severity": "high", "embedding": [0.3, 0.4]},  # synthetic LEIE seed -> replaced
        ],
    }
    real = [{"name": "DEBHANNA AAKER", "tin": "", "npi": None, "source": "oig_leie",
             "severity": "high", "classification": "Individual"}]
    calls = []
    doc = ing.build_reference_doc(current, real, lambda name: calls.append(name) or [9.9, 9.9])

    assert doc["version"] == 5
    names = {e["name"] for e in doc["entries"]}
    assert "Real SAM Vendor LLC" in names            # real SAM preserved
    assert "John Q Public" in names                  # synthetic DMF preserved
    assert "Globex Offshore Inc" not in names        # synthetic LEIE replaced
    assert "DEBHANNA AAKER" in names                 # real LEIE added
    sam = next(e for e in doc["entries"] if e["name"] == "Real SAM Vendor LLC")
    assert sam["embedding"] == [0.5, 0.6]            # preserved entry kept its ORIGINAL embedding
    assert calls == ["DEBHANNA AAKER"]               # only the real LEIE entry was embedded
    assert "REAL public" in doc["sources"]["oig_leie"]  # source description updated to real
    assert doc["semantic_threshold"] == 0.72
