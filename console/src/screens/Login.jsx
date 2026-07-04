import { useState } from "react";
import { login } from "../lib/auth.js";

export default function Login({ onSignedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const u = await login(email, password);
      onSignedIn(u || { username: email });
    } catch (ex) {
      setErr(ex?.message || "Sign in failed");
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
      </div>
    </div>
  );
}
