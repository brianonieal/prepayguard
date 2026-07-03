"""Live e2e client: assumes the payment-submitter role (DEC-5) and SigV4-signs a
POST to the Payment Intake API.

Usage: python scripts/send_payment.py <api_endpoint> <submitter_role_arn> '<payment_json>'
"""
import sys
import urllib.error
from urllib import request as urlreq

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

endpoint, role_arn, payload = sys.argv[1], sys.argv[2], sys.argv[3]
region = "us-east-2"

creds = boto3.client("sts", region_name=region).assume_role(
    RoleArn=role_arn, RoleSessionName="e2e-test"
)["Credentials"]
frozen = boto3.Session(
    aws_access_key_id=creds["AccessKeyId"],
    aws_secret_access_key=creds["SecretAccessKey"],
    aws_session_token=creds["SessionToken"],
    region_name=region,
).get_credentials().get_frozen_credentials()

url = endpoint + "/payments"
signed = AWSRequest(method="POST", url=url, data=payload.encode(),
                    headers={"Content-Type": "application/json"})
SigV4Auth(frozen, "execute-api", region).add_auth(signed)

req = urlreq.Request(url, data=payload.encode(), headers=dict(signed.headers), method="POST")
try:
    resp = urlreq.urlopen(req, timeout=20)
    print(resp.status, resp.read().decode())
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode())
