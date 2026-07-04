// Signed API client. Pulls temporary IAM creds from the Cognito Identity Pool
// (via Amplify) and SigV4-signs every request to API Gateway with aws4fetch.
import { fetchAuthSession } from "aws-amplify/auth";
import { AwsClient } from "aws4fetch";
import { config } from "../config.js";

async function client() {
  const { credentials } = await fetchAuthSession();
  if (!credentials) throw new Error("not signed in");
  return new AwsClient({
    accessKeyId: credentials.accessKeyId,
    secretAccessKey: credentials.secretAccessKey,
    sessionToken: credentials.sessionToken,
    service: "execute-api",
    region: config.region,
  });
}

async function unwrap(res) {
  if (!res.ok) throw new Error(`${res.status} ${await res.text().catch(() => "")}`.trim());
  return res.json();
}

export async function submitPayment(payment) {
  const c = await client();
  return unwrap(await c.fetch(`${config.intakeApi}/payments`, {
    method: "POST", body: JSON.stringify(payment), headers: { "Content-Type": "application/json" },
  }));
}

export async function listReviews() {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/reviews`));
}

export async function getAudit(paymentId) {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/audit/${encodeURIComponent(paymentId)}`));
}

export async function decide(paymentId, body) {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/reviews/${encodeURIComponent(paymentId)}/decision`, {
    method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" },
  }));
}

export async function listAttachments(paymentId) {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/reviews/${encodeURIComponent(paymentId)}/attachments`));
}

export async function presignAttachment(paymentId, filename, contentType) {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/reviews/${encodeURIComponent(paymentId)}/attachments`, {
    method: "POST", body: JSON.stringify({ filename, content_type: contentType }), headers: { "Content-Type": "application/json" },
  }));
}

// Direct PUT to the presigned S3 URL — already authorized, no signing.
export async function uploadFile(url, file) {
  const r = await fetch(url, { method: "PUT", body: file, headers: { "Content-Type": file.type || "application/octet-stream" } });
  if (!r.ok) throw new Error(`upload ${r.status}`);
}
