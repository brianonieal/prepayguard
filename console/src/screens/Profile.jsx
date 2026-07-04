import { useEffect, useState } from "react";
import { currentProfile, mfaPreference, changePassword, startTotpSetup, confirmTotpSetup, disableTotp } from "../lib/auth.js";

const fmt = (d) => (d ? d.toLocaleString() : "-");

export default function Profile({ email, role }) {
  const [p, setP] = useState(null);
  const [mfa, setMfa] = useState({ totpEnabled: false });

  // change-password state
  const [pwOpen, setPwOpen] = useState(false);
  const [pw, setPw] = useState({ old: "", next: "", confirm: "" });
  const [pwMsg, setPwMsg] = useState(null); // {ok} | {error}
  const [pwBusy, setPwBusy] = useState(false);

  // TOTP enrollment state
  const [setup, setSetup] = useState(null); // {secret, uri} once started
  const [code, setCode] = useState("");
  const [mfaMsg, setMfaMsg] = useState(null);
  const [mfaBusy, setMfaBusy] = useState(false);

  useEffect(() => {
    currentProfile().then(setP).catch(() => setP({ sub: "", email, role }));
    mfaPreference().then(setMfa).catch(() => {});
  }, [email, role]);

  const prof = p || { sub: "", email, role, authTime: null, issuedAt: null };
  const roleLabel = prof.role && prof.role !== "none" ? prof.role[0].toUpperCase() + prof.role.slice(1) : "No role";
  const initials = (prof.email || email || "TC").slice(0, 2).toUpperCase();

  const doChangePassword = async (e) => {
    e.preventDefault();
    setPwMsg(null);
    if (pw.next !== pw.confirm) { setPwMsg({ error: "New passwords do not match." }); return; }
    setPwBusy(true);
    try {
      await changePassword(pw.old, pw.next);
      setPwMsg({ ok: "Password changed." });
      setPw({ old: "", next: "", confirm: "" });
      setPwOpen(false);
    } catch (ex) {
      setPwMsg({ error: ex?.message || "Could not change password." });
    } finally {
      setPwBusy(false);
    }
  };

  const beginMfa = async () => {
    setMfaMsg(null); setMfaBusy(true);
    try { setSetup(await startTotpSetup()); }
    catch (ex) { setMfaMsg({ error: ex?.message || "Could not start MFA setup." }); }
    finally { setMfaBusy(false); }
  };

  const confirmMfa = async (e) => {
    e.preventDefault();
    setMfaMsg(null); setMfaBusy(true);
    try {
      await confirmTotpSetup(code.trim());
      setSetup(null); setCode("");
      setMfa(await mfaPreference());
      setMfaMsg({ ok: "MFA enabled. You'll be asked for a code at next sign-in." });
    } catch (ex) {
      setMfaMsg({ error: ex?.message || "Code not accepted." });
    } finally {
      setMfaBusy(false);
    }
  };

  const doDisable = async () => {
    setMfaMsg(null); setMfaBusy(true);
    try { await disableTotp(); setMfa(await mfaPreference()); setMfaMsg({ ok: "MFA disabled." }); }
    catch (ex) { setMfaMsg({ error: ex?.message || "Could not disable MFA." }); }
    finally { setMfaBusy(false); }
  };

  return (
    <div className="body">
      <h2>Profile</h2>
      <div className="sub">Your Amazon Cognito identity. These fields load from your ID token.</div>
      <div className="detail-grid">
        <div>
          <div className="panel">
            <h3>Identity</h3>
            <div className="profile-head">
              <div className="avatar">{initials}</div>
              <div>
                <div className="mono" style={{ fontWeight: 600, fontSize: 15 }}>{prof.email || email}</div>
                <span className="rolebadge">{roleLabel}</span>
              </div>
            </div>
          </div>

          <div className="panel" style={{ marginTop: 14 }}>
            <h3>Password</h3>
            {!pwOpen ? (
              <button className="btn btn-primary btn-sm" onClick={() => { setPwOpen(true); setPwMsg(null); }}>Change password</button>
            ) : (
              <form onSubmit={doChangePassword} className="stack" style={{ maxWidth: 340 }}>
                <div>
                  <label htmlFor="pwold">Current password</label>
                  <input id="pwold" type="password" autoComplete="current-password" value={pw.old}
                    onChange={(e) => setPw({ ...pw, old: e.target.value })} required />
                </div>
                <div>
                  <label htmlFor="pwnew">New password</label>
                  <input id="pwnew" type="password" autoComplete="new-password" value={pw.next}
                    onChange={(e) => setPw({ ...pw, next: e.target.value })} required />
                </div>
                <div>
                  <label htmlFor="pwcon">Confirm new password</label>
                  <input id="pwcon" type="password" autoComplete="new-password" value={pw.confirm}
                    onChange={(e) => setPw({ ...pw, confirm: e.target.value })} required />
                </div>
                <div className="setdesc">At least 12 characters with upper, lower, number, and symbol.</div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn btn-primary btn-sm" type="submit" disabled={pwBusy}>{pwBusy ? "Saving…" : "Update password"}</button>
                  <button className="btn btn-sm" type="button" onClick={() => { setPwOpen(false); setPwMsg(null); }}>Cancel</button>
                </div>
              </form>
            )}
            {pwMsg?.ok && <div className="verdict ok" data-testid="pw-msg">{pwMsg.ok}</div>}
            {pwMsg?.error && <div className="verdict bad" data-testid="pw-msg">{pwMsg.error}</div>}
          </div>

          <div className="panel" style={{ marginTop: 14 }}>
            <h3>Two-factor (TOTP)</h3>
            <dl>
              <dt>Status</dt>
              <dd>{mfa.totpEnabled
                ? <span className="pill p-approved">enabled</span>
                : <span className="pill p-rejected">not enrolled</span>}</dd>
            </dl>
            {!mfa.totpEnabled && !setup && (
              <button className="btn btn-primary btn-sm" onClick={beginMfa} disabled={mfaBusy}>
                {mfaBusy ? "Starting…" : "Enable MFA (TOTP)"}
              </button>
            )}
            {mfa.totpEnabled && (
              <button className="btn btn-red btn-sm" onClick={doDisable} disabled={mfaBusy}>
                {mfaBusy ? "…" : "Disable MFA"}
              </button>
            )}
            {setup && (
              <form onSubmit={confirmMfa} className="stack" style={{ maxWidth: 360, marginTop: 4 }}>
                <div className="setdesc">
                  Add this secret to an authenticator app (Google Authenticator, 1Password, Authy),
                  then enter the 6-digit code it shows.
                </div>
                <div className="hashbox" data-testid="totp-secret">{setup.secret}</div>
                <div>
                  <label htmlFor="totpcode">Code from app</label>
                  <input id="totpcode" inputMode="numeric" autoComplete="one-time-code" value={code}
                    onChange={(e) => setCode(e.target.value)} required />
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn btn-primary btn-sm" type="submit" disabled={mfaBusy}>{mfaBusy ? "Verifying…" : "Verify & enable"}</button>
                  <button className="btn btn-sm" type="button" onClick={() => { setSetup(null); setCode(""); setMfaMsg(null); }}>Cancel</button>
                </div>
              </form>
            )}
            {mfaMsg?.ok && <div className="verdict ok" data-testid="mfa-msg">{mfaMsg.ok}</div>}
            {mfaMsg?.error && <div className="verdict bad" data-testid="mfa-msg">{mfaMsg.error}</div>}
          </div>
        </div>

        <div>
          <div className="panel">
            <h3>Account</h3>
            <dl>
              <dt>Cognito sub</dt><dd className="mono">{prof.sub || "-"}</dd>
              <dt>Role</dt><dd>{roleLabel}</dd>
              <dt>Signed in</dt><dd>{fmt(prof.authTime)}</dd>
              <dt>Token issued</dt><dd>{fmt(prof.issuedAt)}</dd>
              <dt>Status</dt><dd><span className="pill p-approved">active</span></dd>
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}
