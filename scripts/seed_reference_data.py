#!/usr/bin/env python3
"""Seed the reference store with VERSION 1 of the Do Not Pay screening lists.

Publishes the bundled src/component_b_enrichment/reference_data.json (the list
Component B shipped with through v2.0.0) into the versioned store:
  reference/versions/1.json  (immutable history)
  reference/current.json     (the active pointer B fetches)

Idempotent: if current.json already exists, prints its version and exits -
subsequent publishes belong to the admin path (console PUT /reference), never
to this script. Terraform deliberately does not manage these objects.

Usage: python scripts/seed_reference_data.py <bucket-name>
"""
import datetime
import json
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent.parent
CURRENT = "reference/current.json"


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: seed_reference_data.py <reference-bucket-name>")
    bucket = sys.argv[1]
    s3 = boto3.client("s3")

    try:
        existing = json.loads(s3.get_object(Bucket=bucket, Key=CURRENT)["Body"].read())
        print(f"already seeded: version {existing.get('version')} "
              f"({len(existing.get('entries', []))} entries) - nothing to do")
        return
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("NoSuchKey", "404"):
            raise

    bundled = json.loads(
        (ROOT / "src/component_b_enrichment/reference_data.json").read_text(encoding="utf-8"))
    doc = {
        "version": 1,
        "updated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "updated_by": "seed-script (bundled reference_data.json)",
        "sources": bundled["sources"],
        "entries": bundled["entries"],
    }
    body = json.dumps(doc, indent=2).encode()
    s3.put_object(Bucket=bucket, Key="reference/versions/1.json",
                  Body=body, ContentType="application/json")
    s3.put_object(Bucket=bucket, Key=CURRENT, Body=body, ContentType="application/json")
    print(f"seeded version 1: {len(doc['entries'])} entries -> s3://{bucket}/{CURRENT}")


if __name__ == "__main__":
    main()
