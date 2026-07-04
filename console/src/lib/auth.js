// Cognito auth via Amplify: User Pool (SRP login) → Identity Pool (temp IAM
// creds). Those creds are what api.js SigV4-signs with — reusing the DEC-5
// IAM-auth mechanism for the human console.
import { Amplify } from "aws-amplify";
import {
  signIn, signOut, getCurrentUser, fetchAuthSession, confirmSignIn,
  updatePassword, setUpTOTP, verifyTOTPSetup, updateMFAPreference, fetchMFAPreference,
} from "aws-amplify/auth";
import { config } from "../config.js";

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: config.userPoolId,
      userPoolClientId: config.userPoolClientId,
      identityPoolId: config.identityPoolId,
    },
  },
});

// Returns the raw Amplify signIn result ({isSignedIn, nextStep}). With OPTIONAL MFA
// (v3.2.0), an enrolled user gets nextStep CONFIRM_SIGN_IN_WITH_TOTP_CODE — Login.jsx
// then collects the code and calls confirmTotpSignIn(). No MFA → isSignedIn is true.
export async function login(email, password) {
  try { await signOut(); } catch { /* no existing session */ }
  return signIn({ username: email, password });
}

export async function confirmTotpSignIn(code) {
  return confirmSignIn({ challengeResponse: code });
}

// v3.2.0: real Profile fields from the ID token (no hardcoding).
export async function currentProfile() {
  const s = await fetchAuthSession();
  const p = s.tokens?.idToken?.payload || {};
  const g = p["cognito:groups"];
  const groups = Array.isArray(g) ? g : g ? [g] : [];
  return {
    sub: p.sub || "",
    email: p.email || "",
    role: roleFromGroups(groups),
    authTime: p.auth_time ? new Date(p.auth_time * 1000) : null,
    issuedAt: p.iat ? new Date(p.iat * 1000) : null,
  };
}

// v3.2.0: real security actions via Amplify (Cognito). No backend needed.
export async function changePassword(oldPassword, newPassword) {
  await updatePassword({ oldPassword, newPassword });
}

export async function mfaPreference() {
  try {
    const pref = await fetchMFAPreference();
    return { totpEnabled: (pref.enabled || []).includes("TOTP"), preferred: pref.preferred };
  } catch { return { totpEnabled: false, preferred: undefined }; }
}

export async function startTotpSetup() {
  const details = await setUpTOTP();
  return { secret: details.sharedSecret, uri: details.getSetupUri("PrePayGuard").toString() };
}

export async function confirmTotpSetup(code) {
  await verifyTOTPSetup({ code });
  await updateMFAPreference({ totp: "PREFERRED" });
}

export async function disableTotp() {
  await updateMFAPreference({ totp: "DISABLED" });
}

export async function logout() {
  try { await signOut(); } catch { /* ignore */ }
}

export async function currentUser() {
  try { return await getCurrentUser(); } catch { return null; }
}

// v2.0.0: the user's Cognito groups drive role-based UI gating. The groups claim
// also drives cognito:preferred_role → the IAM role the SigV4 calls actually use,
// so the UI and the API authorize on the same signal.
export async function currentGroups() {
  try {
    const s = await fetchAuthSession();
    const g = s.tokens?.idToken?.payload?.["cognito:groups"];
    return Array.isArray(g) ? g : g ? [g] : [];
  } catch { return []; }
}

// Highest-privilege group wins (matches the precedence in console_foundation).
export function roleFromGroups(groups) {
  if (groups.includes("admin")) return "admin";
  if (groups.includes("reviewer")) return "reviewer";
  if (groups.includes("auditor")) return "auditor";
  if (groups.includes("submitter")) return "submitter";
  return "none";
}
