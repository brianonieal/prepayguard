#!/usr/bin/env python3
"""CORS preflight regression guard.

The console is a browser SPA: every authenticated call is preceded by an UNSIGNED
CORS preflight (OPTIONS). SigV4/boto3 test clients do NOT send preflights, so the
Python live-e2e checks can pass while the browser is 100% broken (exactly the
v2.1.x incident). This probes the real OPTIONS preflight on every route and fails
if the Access-Control-Allow-Origin header is missing.

Usage: python scripts/check_cors.py
"""
import sys
from urllib import error as E
from urllib import request as R

ORIGIN = "https://d2rbxaf6pqgvb1.cloudfront.net"
CONSOLE = "https://mdism5yymd.execute-api.us-east-2.amazonaws.com/dev"
INTAKE = "https://0uhsehplg4.execute-api.us-east-2.amazonaws.com/dev"

CASES = [
    ("intake  POST /payments", "POST", f"{INTAKE}/payments"),
    ("console GET  /reviews", "GET", f"{CONSOLE}/reviews"),
    ("console POST /reviews/decisions", "POST", f"{CONSOLE}/reviews/decisions"),
    ("console POST /batches", "POST", f"{CONSOLE}/batches"),
    ("console GET  /batches/x", "GET", f"{CONSOLE}/batches/x"),
    ("console GET  /reference", "GET", f"{CONSOLE}/reference"),
    ("console PUT  /reference", "PUT", f"{CONSOLE}/reference"),
    ("console GET  /audit/x", "GET", f"{CONSOLE}/audit/x"),
    ("console GET  /showcase", "GET", f"{CONSOLE}/showcase"),
]


def preflight(method, url):
    req = R.Request(url, method="OPTIONS", headers={
        "Origin": ORIGIN,
        "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": "content-type,authorization,x-amz-date,x-amz-security-token",
    })
    try:
        resp = R.urlopen(req, timeout=20)
        return resp.status, dict(resp.headers)
    except E.HTTPError as e:
        return e.code, dict(e.headers)


def main():
    failures = 0
    for name, method, url in CASES:
        code, hdrs = preflight(method, url)
        acao = hdrs.get("Access-Control-Allow-Origin") or hdrs.get("access-control-allow-origin")
        ok = code == 200 and acao == ORIGIN
        print(f"{'OK ' if ok else 'FAIL'}  {name:34s} status={code} ACAO={acao!r}")
        failures += 0 if ok else 1
    if failures:
        print(f"\n{failures} preflight(s) failed - browser CORS is broken.")
        sys.exit(1)
    print("\nall CORS preflights OK - the browser can reach every route.")


if __name__ == "__main__":
    main()
