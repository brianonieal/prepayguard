import { useState } from "react";

export default function Login({ onSignIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  return (
    <div className="login-page">
      <header className="topbar">
        <div className="seal">T</div>
        <b>Treasury Console</b>
        <span className="env">DEV · us-east-2</span>
      </header>
      <div className="login-wrap">
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            if (email && password) onSignIn(email);
          }}
        >
          <h2>Sign in</h2>
          <div className="sub">PrePayGuard payment integrity console</div>
          <label htmlFor="email">Email</label>
          <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          <button className="btn btn-primary wide" type="submit">Sign in</button>
          <div className="sub" style={{ marginTop: 14 }}>
            Access is provisioned by the operator.<br />
            Authentication via Amazon Cognito → temporary AWS credentials.
          </div>
        </form>
      </div>
    </div>
  );
}
