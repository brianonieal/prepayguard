import { useState } from "react";

export default function Profile({ email }) {
  const [name, setName] = useState("Brian Onieal");
  const initials = name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase() || "TC";

  return (
    <div className="body">
      <h2>Profile</h2>
      <div className="sub">Backed by your Amazon Cognito user — in v1.4.0 these fields load from your ID token.</div>
      <div className="detail-grid">
        <div>
          <div className="panel">
            <h3>Identity</h3>
            <div className="profile-head">
              <div className="avatar">{initials}</div>
              <div>
                <div style={{ fontWeight: 600, fontSize: 16 }}>{name}</div>
                <div className="mono" style={{ color: "#6b6455", fontSize: 13 }}>{email}</div>
                <span className="rolebadge">Reviewer</span>
              </div>
            </div>
            <label htmlFor="dn">Display name</label>
            <input id="dn" value={name} onChange={(e) => setName(e.target.value)} style={{ maxWidth: 320 }} />
            <div><button className="btn btn-primary btn-sm" style={{ marginTop: 12 }}>Save profile</button></div>
          </div>
          <div className="panel" style={{ marginTop: 14 }}>
            <h3>Security</h3>
            <dl>
              <dt>MFA</dt>
              <dd><span className="pill p-rejected">not enrolled</span>{" "}
                <button className="linkbtn">Enable MFA (TOTP)</button></dd>
              <dt>Password</dt>
              <dd><button className="linkbtn">Change password</button></dd>
            </dl>
          </div>
        </div>
        <div>
          <div className="panel">
            <h3>Account</h3>
            <dl>
              <dt>Cognito sub</dt><dd className="mono">a1b2c3d4-…-9f0e</dd>
              <dt>Role</dt><dd>Reviewer</dd>
              <dt>Created</dt><dd>2026-07-03</dd>
              <dt>Last sign-in</dt><dd>just now · this device</dd>
              <dt>Status</dt><dd><span className="pill p-approved">active</span></dd>
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}
