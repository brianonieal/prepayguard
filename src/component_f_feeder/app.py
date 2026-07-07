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


CONFIG_KEY = "reference/feeder-config/current.json"
# v3.6.0: full USAspending builder. subawards flips prime<->sub; agencies and location
# lists narrow the query; date_type + explicit start/end refine the window.
_CONFIG_FIELDS = ("award_type_codes", "subawards", "date_type", "time_period_days",
                  "start_date", "end_date", "limit", "agencies",
                  "recipient_locations", "place_of_performance_locations")


def _page_for_now() -> int:
    """Deterministic per-hour page so each scheduled run surfaces different awards."""
    return (int(time.time()) // 3600) % _PAGE_ROTATION + 1


def _defaults() -> dict:
    return {"award_type_codes": ["A", "B", "C", "D"], "time_period_days": 365,
            "limit": int(os.environ.get("FEED_LIMIT", "10"))}


def _load_config(event: dict) -> dict:
    """Query filters, in precedence order: an inline event `feeder_config` (admin
    Run-now) > the saved S3 config object (drives scheduled runs, written by the
    console Save) > env defaults (v3.3.0 behavior). The schedule sends no inline
    config, so it reads S3 or falls back to defaults, unchanged."""
    cfg = _defaults()
    inline = event.get("feeder_config")
    if isinstance(inline, dict):
        cfg.update({k: inline[k] for k in _CONFIG_FIELDS if inline.get(k) is not None})
        return cfg
    bucket = os.environ.get("FEEDER_CONFIG_BUCKET")
    if bucket:
        try:
            saved = json.loads(_s3_client().get_object(Bucket=bucket, Key=CONFIG_KEY)["Body"].read())
            cfg.update({k: saved[k] for k in _CONFIG_FIELDS if saved.get(k) is not None})
        except Exception:
            pass  # no saved config yet -> defaults
    return cfg


def _time_period(config: dict) -> dict:
    """Explicit start/end if given, else a look-back window; carry the date_type."""
    today = datetime.datetime.now(datetime.UTC).date()
    if config.get("start_date") and config.get("end_date"):
        start, end = str(config["start_date"]), str(config["end_date"])
    else:
        start = (today - datetime.timedelta(days=int(config.get("time_period_days", 365)))).isoformat()
        end = today.isoformat()
    tp = {"start_date": start, "end_date": end}
    if config.get("date_type"):
        tp["date_type"] = config["date_type"]  # action_date | last_modified_date
    return tp


def _fetch_awards(config: dict) -> list[dict]:
    subawards = bool(config.get("subawards"))
    filters = {"award_type_codes": list(config["award_type_codes"]), "time_period": [_time_period(config)]}
    # Optional narrowing filters (USAspending accepts these on spending_by_award).
    for key in ("agencies", "recipient_locations", "place_of_performance_locations"):
        if config.get(key):
            filters[key] = config[key]
    fields = (["Sub-Award ID", "Sub-Awardee Name", "Sub-Award Amount"] if subawards
              else ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency"])
    body = json.dumps({
        "subawards": subawards, "filters": filters, "fields": fields,
        "limit": int(config["limit"]), "page": config.get("page") or _page_for_now(),
        "sort": "Sub-Award Amount" if subawards else "Award Amount", "order": "desc",
    }).encode()
    req = urllib.request.Request(  # noqa: S310 (fixed https host)
        USASPENDING_URL, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "PrePayGuard-feeder/1.0"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read()).get("results", [])


def _to_payment(award: dict, subawards: bool = False) -> dict | None:
    """Map one USAspending prime award OR sub-award to a payment row, or None to drop
    it. No TIN (USAspending keys on UEI); amount must be positive."""
    if subawards:
        name, aid, amt = award.get("Sub-Awardee Name"), award.get("Sub-Award ID"), award.get("Sub-Award Amount")
        prefix = "USASPEND-SUB-"
    else:
        name, aid, amt = award.get("Recipient Name"), award.get("Award ID"), award.get("Award Amount")
        prefix = "USASPEND-"
    name, aid = str(name or "").strip(), str(aid or "").strip()
    try:
        amount = round(float(amt or 0), 2)
    except (TypeError, ValueError):
        return None
    if not name or not aid or amount <= 0:
        return None
    return {"payment_id": f"{prefix}{aid}", "payee": name, "amount": amount}


def _demo_positive() -> dict:
    """One clearly-labeled test payment to a name on the live Do Not Pay list, so the
    flag/review/semantic path is demonstrable on demand. Never used by the schedule."""
    name = os.environ.get("DEMO_POSITIVE_NAME", "Globex Overseas Incorporated")
    return {"payment_id": f"DEMO-POS-{int(time.time())}", "payee": name, "amount": 100000}


def _build_payments(event: dict) -> tuple[list[dict], str]:
    if event.get("demo_positive"):
        return [_demo_positive()], "demo_positive"
    config = _load_config(event)
    subawards = bool(config.get("subawards"))
    try:
        awards = _fetch_awards(config)
    except Exception as exc:  # never crash the schedule on an upstream hiccup
        print(f"feeder: USAspending fetch failed, skipping run: {type(exc).__name__}: {exc}")
        return [], "fetch_error"
    payments = [p for a in awards if (p := _to_payment(a, subawards)) is not None]
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
