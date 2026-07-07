import { useEffect, useState } from "react";
import Login from "./screens/Login.jsx";
import Submit from "./screens/Submit.jsx";
import ReviewQueue from "./screens/ReviewQueue.jsx";
import AuditDetail from "./screens/AuditDetail.jsx";
import Profile from "./screens/Profile.jsx";
import Settings from "./screens/Settings.jsx";
import ReferenceData from "./screens/ReferenceData.jsx";
import Feed from "./screens/Feed.jsx";
import Analytics from "./screens/Analytics.jsx";
import Showcase from "./screens/Showcase.jsx";
import UserMenu from "./components/UserMenu.jsx";
import { currentUser, logout, currentGroups, roleFromGroups } from "./lib/auth.js";

export function nav(hash) {
  window.location.hash = hash;
  window.dispatchEvent(new Event("hashchange"));
}

const DEFAULT_SETTINGS = { density: "comfortable", defaultFilter: "pending" };
function loadSettings() {
  try { return { ...DEFAULT_SETTINGS, ...JSON.parse(localStorage.getItem("tc.settings") || "{}") }; }
  catch { return DEFAULT_SETTINGS; }
}

function useHashParts() {
  const read = () => (window.location.hash || "#/submit").replace(/^#\/?/, "").split("/").filter(Boolean);
  const [parts, setParts] = useState(read);
  useEffect(() => {
    const on = () => setParts(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return parts.length ? parts : ["submit"];
}

export default function App() {
  const [user, setUser] = useState(undefined); // undefined=checking, null=out, obj=in
  const [role, setRole] = useState(null);      // null=unknown; submitter|reviewer|admin|none
  const [settings, setSettingsState] = useState(loadSettings);
  const parts = useHashParts();
  const setSettings = (patch) =>
    setSettingsState((s) => {
      const n = { ...s, ...patch };
      try { localStorage.setItem("tc.settings", JSON.stringify(n)); } catch { /* ignore */ }
      return n;
    });

  useEffect(() => { currentUser().then((u) => setUser(u)).catch(() => setUser(null)); }, []);
  // Resolve the role from Cognito groups once signed in (drives nav + guards).
  useEffect(() => {
    if (user) currentGroups().then((g) => setRole(roleFromGroups(g))).catch(() => setRole("none"));
    else setRole(null);
  }, [user]);

  const canSubmit = ["submitter", "reviewer", "admin"].includes(role);
  const canReview = ["reviewer", "admin", "auditor"].includes(role); // auditor views read-only
  const canDecide = ["reviewer", "admin"].includes(role);
  const canAnalytics = ["admin", "auditor"].includes(role);
  const isAdmin = role === "admin";
  const landing = canSubmit ? "#/submit" : canAnalytics ? "#/analytics" : canReview ? "#/reviews" : "#/profile";
  // Role guards: bounce a user off any route their role can't see.
  useEffect(() => {
    if (!user || !role) return;
    const r = parts[0];
    if ((r === "submit" && !canSubmit) || (r === "reviews" && !canReview) ||
        (r === "reference" && !isAdmin) || (r === "feed" && !isAdmin) ||
        (r === "analytics" && !canAnalytics) || (r === "showcase" && !canReview)) {
      nav(landing);
    }
  }, [user, role, parts]); // eslint-disable-line

  if (user === undefined) {
    return <div className="login-page"><div className="login-wrap"><div className="sub">Loading…</div></div></div>;
  }
  if (!user) {
    const landing = (h) => (!h || h === "#" || h === "#/") ? "#/submit" : h;
    return <Login onSignedIn={(u) => { setUser(u); nav(landing(window.location.hash)); }} />;
  }

  const route = parts[0];
  const onReviews = route === "reviews";
  const detailId = onReviews ? parts[1] : null;
  const signOut = async () => { await logout(); setUser(null); };
  const emailLabel = user?.signInDetails?.loginId || user?.username || "signed in";

  return (
    <div className={`app ${settings.density === "compact" ? "compact" : ""}`}>
      <header className="topbar">
        <div className="seal">T</div>
        <b>Treasury Console</b>
        <span className="env">DEV · us-east-2</span>
        {role && role !== "none" && <span className="rolechip" data-testid="role-chip">{role}</span>}
        <UserMenu email={emailLabel} onNav={nav} onSignOut={signOut} />
      </header>
      <nav className="tabs">
        {canSubmit && (
          <button className={route === "submit" ? "on" : ""} onClick={() => nav("#/submit")}>Submit Payment</button>
        )}
        {canReview && (
          <button className={onReviews ? "on" : ""} onClick={() => nav("#/reviews")}>Review Queue</button>
        )}
        {canReview && (
          <button className={route === "showcase" ? "on" : ""} onClick={() => nav("#/showcase")}>Overview</button>
        )}
        {canAnalytics && (
          <button className={route === "analytics" ? "on" : ""} onClick={() => nav("#/analytics")}>Analytics</button>
        )}
        {isAdmin && (
          <button className={route === "reference" ? "on" : ""} onClick={() => nav("#/reference")}>Reference Data</button>
        )}
        {isAdmin && (
          <button className={route === "feed" ? "on" : ""} onClick={() => nav("#/feed")}>Feed</button>
        )}
      </nav>
      <main className="content">
        {route === "showcase" && canReview && <Showcase />}
        {route === "submit" && canSubmit && <Submit />}
        {onReviews && canReview && !detailId && <ReviewQueue defaultFilter={settings.defaultFilter} canDecide={canDecide} onOpen={(id) => nav(`#/reviews/${id}`)} />}
        {onReviews && canReview && detailId && <AuditDetail paymentId={detailId} canDecide={canDecide} onBack={() => nav("#/reviews")} />}
        {route === "analytics" && canAnalytics && <Analytics />}
        {route === "reference" && isAdmin && <ReferenceData />}
        {route === "feed" && isAdmin && <Feed />}
        {route === "profile" && <Profile email={emailLabel} role={role} />}
        {route === "settings" && <Settings settings={settings} onChange={setSettings} isAdmin={isAdmin} />}
      </main>
      <footer className="foot">
        <span>Treasury Console · v3.2.1</span>
        <span>DEV · us-east-2</span>
        <span>Records are immutably audited · S3 Object Lock (COMPLIANCE)</span>
      </footer>
    </div>
  );
}
