"""Component F - Scheduled Feeder (v3.3.0, automated real-data feed).

An EventBridge scheduled rule invokes this handler hourly. Each run pulls a page of
real federal awards from the public, keyless USAspending API, maps each to a payment
row, and writes ONE JSON file to the batch-imports bucket. Component E's existing
S3 trigger (DEC-16) then ingests it and the whole pipeline screens every row, so real
payees flow into the console with no human upload.

Design notes:
- The SCHEDULED feed is 100% real USAspending data. A manual invoke with
  {"demo_positive": true} instead appends ONE clearly-labeled test payment (payment_id
  prefixed DEMO-POS-) to a name already on the live Do Not Pay list, so the flag /
  review / semantic path can be shown on cue WITHOUT contaminating the real feed.
- payment_id is derived deterministically from the USAspending Award ID, so the same
  award pulled on two runs dedupes via the SHARED idempotency table (Component A/E) -
  no double screening.
- The page advances by the hour so each run surfaces fresh payees rather than the same
  top awards every time.
- A USAspending error is logged and the run is skipped (no file written); it never
  raises, so a bad upstream hour cannot error-spam the schedule.
- Real payment data is public but permanent once screened (Object Lock audit record);
  the feed is volume-capped (FEED_LIMIT) and meant for the dev audit bucket (1-day
  retention). See DEC-23.
"""
from __future__ import annotations

import datetime
import json
import os
import time
import urllib.request

import boto3

_s3 = None

USASPENDING_URL = os.environ.get(
    "USASPENDING_URL", "https://api.usaspending.gov/api/v2/search/spending_by_award/")
BATCH_PREFIX = "batch-imports"
_PAGE_ROTATION = 500  # rotate through this many pages, one per hour, for variety


def _s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _window():
    today = datetime.datetime.now(datetime.UTC).date()
    return (today - datetime.timedelta(days=365)).isoformat(), today.isoformat()


def _page_for_now() -> int:
    """Deterministic per-hour page so each scheduled run surfaces different awards."""
    return (int(time.time()) // 3600) % _PAGE_ROTATION + 1


def _fetch_awards(limit: int, page: int) -> list[dict]:
    start, end = _window()
    body = json.dumps({
        "filters": {"award_type_codes": ["A", "B", "C", "D"],
                    "time_period": [{"start_date": start, "end_date": end}]},
        "fields": ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency"],
        "limit": limit, "page": page, "sort": "Award Amount", "order": "desc",
    }).encode()
    req = urllib.request.Request(  # noqa: S310 (fixed https host)
        USASPENDING_URL, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "PrePayGuard-feeder/1.0"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read()).get("results", [])


def _to_payment(award: dict) -> dict | None:
    """Map one USAspending award to a payment row, or None to drop it. No TIN (SAM/
    USAspending key on UEI); amount must be positive."""
    name = str(award.get("Recipient Name") or "").strip()
    aid = str(award.get("Award ID") or "").strip()
    try:
        amount = round(float(award.get("Award Amount") or 0), 2)
    except (TypeError, ValueError):
        return None
    if not name or not aid or amount <= 0:
        return None
    return {"payment_id": f"USASPEND-{aid}", "payee": name, "amount": amount}


def _demo_positive() -> dict:
    """One clearly-labeled test payment to a name on the live Do Not Pay list, so the
    flag/review/semantic path is demonstrable on demand. Never used by the schedule."""
    name = os.environ.get("DEMO_POSITIVE_NAME", "Globex Overseas Incorporated")
    return {"payment_id": f"DEMO-POS-{int(time.time())}", "payee": name, "amount": 100000}


def _build_payments(event: dict) -> tuple[list[dict], str]:
    if event.get("demo_positive"):
        return [_demo_positive()], "demo_positive"
    limit = int(os.environ.get("FEED_LIMIT", "10"))
    try:
        awards = _fetch_awards(limit, _page_for_now())
    except Exception as exc:  # never crash the schedule on an upstream hiccup
        print(f"feeder: USAspending fetch failed, skipping run: {type(exc).__name__}: {exc}")
        return [], "fetch_error"
    payments = [p for a in awards if (p := _to_payment(a)) is not None]
    return payments, "usaspending"


def handler(event, context=None):
    event = event or {}
    payments, source = _build_payments(event)
    if not payments:
        print(f"feeder: nothing to write (source={source})")
        return {"written": 0, "source": source}
    batch_id = f"feed-{int(time.time())}"
    key = f"{BATCH_PREFIX}/{batch_id}/payments.json"
    _s3_client().put_object(
        Bucket=os.environ["BATCH_BUCKET"], Key=key,
        Body=json.dumps({"payments": payments}).encode(), ContentType="application/json")
    print(f"feeder: wrote {len(payments)} payments (source={source}) to {key}")
    return {"written": len(payments), "source": source, "key": key}
