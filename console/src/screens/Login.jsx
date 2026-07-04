import { useState } from "react";
import { login, confirmTotpSignIn, currentUser } from "../lib/auth.js";

export default function Login({ onSignedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [mfaStep, setMfaStep] = useState(false); // TOTP challenge for enrolled users
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const finish = async () => onSignedIn((await currentUser()) || { username: email });

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      const res = await login(email, password);
      if (res?.isSignedIn) await finish();
      else if (res?.nextStep?.signInStep === "CONFIRM_SIGN_IN_WITH_TOTP_CODE") setMfaStep(true);
      else setErr(`Unsupported sign-in step: ${res?.nextStep?.signInStep || "unknown"}`);
    } catch (ex) {
      setErr(ex?.message || "Sign in failed");
    } finally {
      setBusy(false);
    }
  };

  const submitMfa = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      const res = await confirmTotpSignIn(code.trim());
      if (res?.isSignedIn) await finish();
      else setErr("Code not accepted. Try again.");
    } catch (ex) {
      setErr(ex?.message || "Invalid code");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <header className="topbar">
        <div className="seal">T</div>
        <b>Treasury Console</b>
        <span className="env">DEV · us-east-2</span>
      </header>
      <div className="login-wrap">
        {!mfaStep ? (
          <form className="card" onSubmit={submit}>
            <h2>Sign in</h2>
            <div className="sub">PrePayGuard payment integrity console</div>
            {err && <div className="verdict bad" style={{ marginTop: 12 }}>{err}</div>}
            <label htmlFor="email">Email</label>
            <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="username" />
            <label htmlFor="password">Password</label>
            <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
            <button className="btn btn-primary wide" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
            <div className="sub" style={{ marginTop: 14 }}>
              Access is provisioned by the operator.<br />
              Authentication via Amazon Cognito → temporary AWS credentials.
            </div>
          </form>
        ) : (
          <form className="card" onSubmit={submitMfa}>
            <h2>Two-factor code</h2>
            <div className="sub">Enter the 6-digit code from your authenticator app.</div>
            {err && <div className="verdict bad" style={{ marginTop: 12 }}>{err}</div>}
            <label htmlFor="code">Authentication code</label>
            <input id="code" inputMode="numeric" autoComplete="one-time-code" value={code}
              onChange={(e) => setCode(e.target.value)} required autoFocus />
            <button className="btn btn-primary wide" type="submit" disabled={busy}>{busy ? "Verifying…" : "Verify"}</button>
            <div className="sub" style={{ marginTop: 14 }}>
              <button type="button" className="linkbtn" onClick={() => { setMfaStep(false); setCode(""); setErr(""); }}>
                Back to sign in
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
