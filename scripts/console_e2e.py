"""Live e2e proof of the CONSOLE auth path — exactly what the browser does:
Cognito User Pool login -> Identity Pool temp IAM creds -> SigV4 to the intake
and console APIs. Proves the wired console works against the deployed backend.

Usage: python scripts/console_e2e.py
"""
import json
import time
import urllib.error
from urllib import request as urlreq

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

REGION = "us-east-2"
POOL = "us-east-2_0jEWxXtcn"
CLIENT = "7he6tfbthdhrqc2kdolkm29okn"
IDPOOL = "us-east-2:1ac5c956-6c51-4f4d-91b4-6ada417fd9cc"
USER = "brian.onieal@gmail.com"
PW = "Treasury#Demo2026"
INTAKE = "https://0uhsehplg4.execute-api.us-east-2.amazonaws.com/dev"
CONSOLE = "https://mdism5yymd.execute-api.us-east-2.amazonaws.com/dev"

# 1. Cognito User Pool login (USER_PASSWORD flow).
idp = boto3.client("cognito-idp", region_name=REGION)
auth = idp.initiate_auth(ClientId=CLIENT, AuthFlow="USER_PASSWORD_AUTH",
                         AuthParameters={"USERNAME": USER, "PASSWORD": PW})
id_token = auth["AuthenticationResult"]["IdToken"]
print("1. Cognito login: OK")

# 2. Identity Pool -> temporary IAM credentials for the authenticated role.
ident = boto3.client("cognito-identity", region_name=REGION)
provider = f"cognito-idp.{REGION}.amazonaws.com/{POOL}"
idid = ident.get_id(IdentityPoolId=IDPOOL, Logins={provider: id_token})["IdentityId"]
c = ident.get_credentials_for_identity(IdentityId=idid, Logins={provider: id_token})["Credentials"]
sess = boto3.Session(aws_access_key_id=c["AccessKeyId"], aws_secret_access_key=c["SecretKey"],
                     aws_session_token=c["SessionToken"], region_name=REGION)
frozen = sess.get_credentials().get_frozen_credentials()
print("2. Identity Pool temp creds: OK")


def call(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = AWSRequest(method=method, url=url, data=data,
                     headers={"Content-Type": "application/json"} if data else {})
    SigV4Auth(frozen, "execute-api", REGION).add_auth(req)
    r = urlreq.Request(url, data=data, headers=dict(req.headers), method=method)
    try:
        resp = urlreq.urlopen(r, timeout=25)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


pid = f"console-live-{int(time.time())}"
s, b = call("POST", f"{INTAKE}/payments", {"payment_id": pid, "payee": "Acme Shell LLC", "amount": 250})
print(f"3. Submit (SigV4 as console user): {s} {b}")

print("   waiting for pipeline…")
time.sleep(14)

s, b = call("GET", f"{CONSOLE}/reviews")
mine = [r for r in b.get("reviews", []) if r["payment_id"] == pid]
print(f"4. GET /reviews: {s}, our item present: {bool(mine)} -> {mine[0] if mine else None}")

s, audit = call("GET", f"{CONSOLE}/audit/{pid}")
print(f"5. GET /audit/{pid}: {s}, disposition={audit.get('record', {}).get('decision', {}).get('disposition')}")

s, dec = call("POST", f"{CONSOLE}/reviews/{pid}/decision", {"decision": "approved", "note": "e2e verified"})
print(f"6. POST decision (approve): {s} {dec}")

s, after = call("GET", f"{CONSOLE}/reviews")
row = next((r for r in after.get("reviews", []) if r["payment_id"] == pid), {})
ok = row.get("status") == "approved"
print(f"7. Status after decision: {row.get('status')}  -> {'PASS' if ok else 'FAIL'}")
