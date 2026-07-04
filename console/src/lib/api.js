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

export async function listReviews({ status, cursor, limit = 25 } = {}) {
  const c = await client();
  const qs = new URLSearchParams();
  if (status && status !== "all") qs.set("status", status);
  if (cursor) qs.set("cursor", cursor);
  qs.set("limit", String(limit));
  return unwrap(await c.fetch(`${config.consoleApi}/reviews?${qs}`));
}

export async function getAudit(paymentId) {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/audit/${encodeURIComponent(paymentId)}`));
}

// v2.3.0: on-demand advisory LLM brief. Read-only; never part of the audit record.
export async function getBrief(paymentId) {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/reviews/${encodeURIComponent(paymentId)}/brief`));
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

// v1.6.0 batch ingestion: presign a CSV upload, then poll its server-side summary.
export async function presignBatch(filename) {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/batches`, {
    method: "POST", body: JSON.stringify({ filename }), headers: { "Content-Type": "application/json" },
  }));
}

export async function getBatch(batchId) {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/batches/${encodeURIComponent(batchId)}`));
}

export async function listBatches() {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/batches`));
}

// v2.1.0 reference-data lifecycle: view the active screening list, publish new
// versions (admin-only), browse the immutable version history.
export async function getReference() {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/reference`));
}

export async function putReference(doc) {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/reference`, {
    method: "PUT", body: JSON.stringify(doc), headers: { "Content-Type": "application/json" },
  }));
}

export async function listReferenceVersions() {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/reference/versions`));
}

export async function getReferenceVersion(n) {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/reference/versions/${n}`));
}

// v2.4.0 analytics & compliance (admin + read-only auditor).
export async function getAnalytics() {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/analytics`));
}

export async function getAuditLog({ disposition, limit = 200 } = {}) {
  const c = await client();
  const qs = new URLSearchParams();
  if (disposition && disposition !== "all") qs.set("disposition", disposition);
  qs.set("limit", String(limit));
  return unwrap(await c.fetch(`${config.consoleApi}/audit-log?${qs}`));
}

// v3.0.0 executive showcase: the narrative Overview tab's single data call
// (summary + match-type tally + one worked example per disposition, live).
export async function getShowcase() {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/showcase`));
}

// v3.1.0 demo reset: admin-only. Clears the working tables (reviews / audit_index /
// batches / idempotency) so a demo starts from zero; the immutable S3 audit is
// untouched. Requires the typed confirmation the server also checks.
export async function resetData() {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/admin/reset`, {
    method: "POST", body: JSON.stringify({ confirm: "RESET" }), headers: { "Content-Type": "application/json" },
  }));
}

// v1.6.0 bulk review actions: one decision applied to many payments.
export async function bulkDecide(paymentIds, decision, note = "") {
  const c = await client();
  return unwrap(await c.fetch(`${config.consoleApi}/reviews/decisions`, {
    method: "POST", body: JSON.stringify({ payment_ids: paymentIds, decision, note }),
    headers: { "Content-Type": "application/json" },
  }));
}
