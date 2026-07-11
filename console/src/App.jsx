import { useEffect, useState } from "react";
import Login from "./screens/Login.jsx";
import ReviewQueue from "./screens/ReviewQueue.jsx";
import AuditDetail from "./screens/AuditDetail.jsx";
import Profile from "./screens/Profile.jsx";
import Settings from "./screens/Settings.jsx";
import Admin from "./screens/Admin.jsx";
import Analytics from "./screens/Analytics.jsx";
import Dashboard from "./screens/Dashboard.jsx";
import Tour from "./screens/Tour.jsx";
import Pitch from "./screens/Pitch.jsx";
import TreasuryNews from "./screens/TreasuryNews.jsx";
import SubmitModal from "./components/SubmitModal.jsx";
import UserMenu from "./components/UserMenu.jsx";
import { currentUser, logout, currentGroups, roleFromGroups } from "./lib/auth.js";

export function nav(hash) {
  window.location.hash = hash;
  window.dispatchEvent(new Event("hashchange"));
}

const PREVIEW_ROLES = ["reviewer", "auditor", "submitter"];
const cap = (s) => s[0].toUpperCase() + s.slice(1);

const DEFAULT_SETTINGS = { density: "comfortable", defaultFilter: "pending" };
function loadSettings() {
  try { return { ...DEFAULT_SETTINGS, ...JSON.parse(localStorage.getItem("tc.settings") || "{}") }; }
  catch { return DEFAULT_SETTINGS; }
}

function useHashParts() {
  const read = () => (window.location.hash || "#/dashboard").replace(/^#\/?/, "").split("/").filter(Boolean);
  const [parts, setParts] = useState(read);
  useEffect(() => {
    const on = () => setParts(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return parts.length ? parts : ["dashboard"];
}

export default function App() {
  const [user, setUser] = useState(undefined); // undefined=checking, null=out, obj=in
  const [role, setRole] = useState(null);      // null=unknown; submitter|reviewer|admin|auditor|none
  // Admin-only role-preview simulation (rendering only). NEVER read by an API call or the
  // Cognito session: `role` above is the sole signal that drives cognito:preferred_role and
  // therefore real SigV4 authorization (lib/auth.js). previewRole only feeds the derived
  // UI booleans below, so a previewed restriction is exactly that: hidden/disabled controls,
  // not a real permission change. null = no preview (showing the real admin view).
  const [previewRole, setPreviewRole] = useState(null); // null|"reviewer"|"auditor"|"submitter"
  const [settings, setSettingsState] = useState(loadSettings);
  const [submitOpen, setSubmitOpen] = useState(false);
  const parts = useHashParts();
  const setSettings = (patch) =>
    setSettingsState((s) => {
      const n = { ...s, ...patch };
      try { localStorage.setItem("tc.settings", JSON.stringify(n)); } catch { /* ignore */ }
      return n;
    });

  useEffect(() => { currentUser().then((u) => setUser(u)).catch(() => setUser(null)); }, []);
  useEffect(() => {
    if (user) currentGroups().then((g) => setRole(roleFromGroups(g))).catch(() => setRole("none"));
    else setRole(null);
  }, [user]);
  // Safety net: a preview can only ever exist under a genuine admin session. If the real
  // role is ever anything else (session change, role revoked), drop any active preview.
  useEffect(() => { if (role !== "admin") setPreviewRole(null); }, [role]);

  // Every gating boolean below reads effectiveRole, never the real `role` directly, so
  // toggling the preview dropdown changes exactly what renders and nothing else.
  const effectiveRole = role === "admin" && previewRole ? previewRole : role;
  const canSubmit = ["submitter", "reviewer", "admin"].includes(effectiveRole);
  const canReview = ["reviewer", "admin", "auditor"].includes(effectiveRole); // auditor views read-only
  const canDecide = ["reviewer", "admin"].includes(effectiveRole);
  const canAnalytics = ["admin", "auditor"].includes(effectiveRole);
  const isAdmin = effectiveRole === "admin";
  const landing = canReview ? "#/dashboard" : "#/tour";
  // Role guards: bounce a user off any route their (effective) role can't see. Tour is open
  // to all. Depends on previewRole so switching the preview re-evaluates the current route
  // exactly as it would for a real session in that role.
  useEffect(() => {
    if (!user || !role) return;
    const r = parts[0];
    if ((r === "dashboard" && !canReview) || (r === "reviews" && !canReview) ||
        ((r === "admin" || r === "reference" || r === "feed") && !isAdmin) ||
        (r === "analytics" && !canAnalytics)) {
      nav(landing);
    }
  }, [user, role, previewRole, parts]); // eslint-disable-line

  if (user === undefined) {
    return <div className="login-page"><div className="login-wrap"><div className="sub">Loading…</div></div></div>;
  }
  if (!user) {
    const to = (h) => (!h || h === "#" || h === "#/") ? "#/dashboard" : h;
    return <Login onSignedIn={(u) => { setUser(u); nav(to(window.location.hash)); }} />;
  }

  const route = parts[0];
  const onReviews = route === "reviews";
  const onAdmin = route === "admin" || route === "reference" || route === "feed";
  const detailId = onReviews ? parts[1] : null;
  const signOut = async () => { await logout(); setUser(null); };
  const emailLabel = user?.signInDetails?.loginId || user?.username || "signed in";

  return (
    <div className={`app ${settings.density === "compact" ? "compact" : ""}`}>
      <header className="topbar">
        <div className="brandmark">PG</div>
        <div className="brand">
          <b>PrePayGuard</b>
          <span className="brand-sub">Treasury payment integrity console</span>
        </div>
        {role && role !== "none" && <span className="rolechip" data-testid="role-chip">{effectiveRole}</span>}
        {role === "admin" && (
          <select className="rolepreview" aria-label="Preview console as role" data-testid="role-preview-select"
            value={previewRole || "admin"}
            onChange={(e) => setPreviewRole(e.target.value === "admin" ? null : e.target.value)}>
            <option value="admin">Admin (real)</option>
            {PREVIEW_ROLES.map((r) => <option key={r} value={r}>Preview: {cap(r)}</option>)}
          </select>
        )}
        <div className="topbar-spacer" />
        <UserMenu email={emailLabel} onNav={nav} onSignOut={signOut}
          onSubmit={canSubmit ? () => setSubmitOpen(true) : undefined} />
      </header>
      {previewRole && (
        <div className="preview-banner" role="status" data-testid="role-preview-banner">
          Previewing as: <b>{cap(previewRole)}</b>. Your actual access remains Admin.
          <button className="preview-exit" onClick={() => setPreviewRole(null)}>Exit preview</button>
        </div>
      )}
      <nav className="tabs">
        {/* Nav order: Pitch, Dashboard, Admin, Audit log, Review Queue, Treasury News (last).
            Pitch and Treasury News are open to any authenticated user; the rest keep their role
            gates. Treasury News is read-only and shares no code path with the screening pipeline. */}
        <button className={route === "pitch" ? "on" : ""} onClick={() => nav("#/pitch")}>Pitch</button>
        {canReview && (
          <button className={route === "dashboard" ? "on" : ""} onClick={() => nav("#/dashboard")}>Dashboard</button>
        )}
        {isAdmin && (
          <button className={onAdmin ? "on" : ""} onClick={() => nav("#/admin")}>Admin</button>
        )}
        {canAnalytics && (
          <button className={route === "analytics" ? "on" : ""} onClick={() => nav("#/analytics")}>Audit log</button>
        )}
        {canReview && (
          <button className={onReviews ? "on" : ""} onClick={() => nav("#/reviews")}>Review Queue</button>
        )}
        <button className={route === "news" ? "on" : ""} onClick={() => nav("#/news")}>Treasury News</button>
      </nav>
      <main className="content">
        {route === "dashboard" && canReview && <Dashboard onNav={nav} />}
        {onReviews && canReview && !detailId && <ReviewQueue defaultFilter={settings.defaultFilter} canDecide={canDecide} onOpen={(id) => nav(`#/reviews/${id}`)} />}
        {onReviews && canReview && detailId && <AuditDetail paymentId={detailId} canDecide={canDecide} onBack={() => nav("#/reviews")} />}
        {route === "analytics" && canAnalytics && <Analytics />}
        {onAdmin && isAdmin && <Admin initial={route === "reference" ? "reference" : "feed"} />}
        {route === "tour" && <Tour onNav={nav} canReview={canReview} isAdmin={isAdmin} />}
        {route === "pitch" && <Pitch />}
        {route === "news" && <TreasuryNews />}
        {route === "profile" && <Profile email={emailLabel} role={role} />}
        {route === "settings" && <Settings settings={settings} onChange={setSettings} isAdmin={isAdmin} />}
      </main>
      {submitOpen && <SubmitModal onClose={() => setSubmitOpen(false)} />}
      <footer className="foot">
        <span>PrePayGuard · v3.8.3</span>
        <span>DEV · us-east-2</span>
        <span>Records are immutably audited · S3 Object Lock (COMPLIANCE)</span>
      </footer>
    </div>
  );
}
