"""Component C — risk scoring & three-way disposition (DEC-14)."""
import json


def _sqs_event(*payments):
    return {"Records": [{"messageId": f"m{i}", "body": json.dumps(p)} for i, p in enumerate(payments)]}


def _drain(sqs, url):
    msgs = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10).get("Messages", [])
    return [json.loads(m["Body"]) for m in msgs]


def _enriched(payment_id, matches):
    return {
        "payment_id": payment_id, "amount": 10, "payee": "X",
        "enrichment": {
            "matches": matches,
            "match_count": len(matches),
            "highest_confidence": max((m["confidence"] for m in matches), default=0),
        },
    }


def test_no_match_approves(worker):
    app = worker["load"]("component_c_risk_scoring")
    app.handler(_sqs_event(_enriched("p1", [])))
    assert _drain(worker["sqs"], worker["out_url"])[0]["risk"]["disposition"] == "approve"


def test_tin_match_rejects(worker):
    app = worker["load"]("component_c_risk_scoring")
    matches = [{"source": "death_master_file", "matched_on": "tin", "confidence": 95, "severity": "high"}]
    out = _drain_after(app, worker, _enriched("p2", matches))
    assert out["risk"]["disposition"] == "reject"


def test_name_match_routes_to_review(worker):
    # A name-only match is a POTENTIAL match: identity-uncertain, so a human
    # decides. This is what feeds commitment 2's human-review path at Component D.
    app = worker["load"]("component_c_risk_scoring")
    matches = [{"source": "sam_exclusions", "matched_on": "name_exact", "confidence": 80, "severity": "high"}]
    out = _drain_after(app, worker, _enriched("p3", matches))
    assert out["risk"]["disposition"] == "review"


def test_fuzzy_name_match_also_reviews(worker):
    app = worker["load"]("component_c_risk_scoring")
    matches = [{"source": "oig_leie", "matched_on": "name_fuzzy", "confidence": 60, "severity": "high"}]
    out = _drain_after(app, worker, _enriched("p4", matches))
    assert out["risk"]["disposition"] == "review"


def _drain_after(app, worker, payment):
    app.handler(_sqs_event(payment))
    return _drain(worker["sqs"], worker["out_url"])[0]
