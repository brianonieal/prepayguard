"""Live commitment-4 proof: writes an object to the REAL audit bucket and shows
S3 Object Lock (COMPLIANCE) refuses to delete it or shorten its retention.

Usage: python scripts/live_object_lock_proof.py <bucket_name> [region]
Exit 0 = immutability proven. Leaves one locked object (self-expires at the
bucket's retention period). Uses real AWS credentials - not run in CI.
"""
import datetime
import json
import sys

import boto3
from botocore.exceptions import ClientError

bucket = sys.argv[1]
region = sys.argv[2] if len(sys.argv) > 2 else "us-east-2"
s3 = boto3.client("s3", region_name=region)

key = "audit/live-proof/immutability-check.json"
body = json.dumps({"proof": "object-lock-compliance", "component": "audit_store"}).encode()

put = s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
version = put["VersionId"]

r = {"bucket": bucket, "key": key, "version_id": version}

# 1. Real S3 auto-applies the bucket's default COMPLIANCE retention on write.
retention = s3.get_object_retention(Bucket=bucket, Key=key)["Retention"]
r["retention_mode"] = retention.get("Mode")
r["retain_until"] = str(retention.get("RetainUntilDate"))

# 2. Deleting the locked version must be refused.
try:
    s3.delete_object(Bucket=bucket, Key=key, VersionId=version)
    r["delete_denied"] = False
except ClientError as e:
    r["delete_denied"] = e.response["Error"]["Code"] == "AccessDenied"
    r["delete_error_code"] = e.response["Error"]["Code"]

# 3. Shortening the retention must be refused (COMPLIANCE cannot be reduced).
try:
    s3.put_object_retention(
        Bucket=bucket, Key=key, VersionId=version,
        Retention={"Mode": "COMPLIANCE", "RetainUntilDate": datetime.datetime.now(datetime.timezone.utc)},
    )
    r["shorten_denied"] = False
except ClientError as e:
    r["shorten_denied"] = e.response["Error"]["Code"] == "AccessDenied"
    r["shorten_error_code"] = e.response["Error"]["Code"]

print(json.dumps(r, indent=2))
ok = r.get("retention_mode") == "COMPLIANCE" and r.get("delete_denied") and r.get("shorten_denied")
print("LIVE OBJECT LOCK PROOF:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
