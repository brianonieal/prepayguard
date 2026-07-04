// Cognito auth via Amplify: User Pool (SRP login) → Identity Pool (temp IAM
// creds). Those creds are what api.js SigV4-signs with — reusing the DEC-5
// IAM-auth mechanism for the human console.
import { Amplify } from "aws-amplify";
import { signIn, signOut, getCurrentUser } from "aws-amplify/auth";
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
