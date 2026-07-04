// Cognito auth via Amplify: User Pool (SRP login) → Identity Pool (temp IAM
// creds). Those creds are what api.js SigV4-signs with — reusing the DEC-5
// IAM-auth mechanism for the human console.
import { Amplify } from "aws-amplify";
import { signIn, signOut, getCurrentUser, fetchAuthSession } from "aws-amplify/auth";
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

export async function login(email, password) {
  try { await signOut(); } catch { /* no existing session */ }
  await signIn({ username: email, password });
  return getCurrentUser();
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
