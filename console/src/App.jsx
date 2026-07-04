import { useEffect, useState } from "react";
import Login from "./screens/Login.jsx";
import Submit from "./screens/Submit.jsx";
import ReviewQueue from "./screens/ReviewQueue.jsx";
import AuditDetail from "./screens/AuditDetail.jsx";
import Profile from "./screens/Profile.jsx";
import Settings from "./screens/Settings.jsx";
import UserMenu from "./components/UserMenu.jsx";
import { FAKE_REVIEWS } from "./fakeData.js";

// Hash routing: deep-linkable, and works on static S3+CloudFront hosting with
// no error-page rewrites. Routes: #/submit · #/reviews · #/reviews/:id ·
// #/profile · #/settings
export function nav(hash) {
  window.location.hash = hash;
  window.dispatchEvent(new Event("hashchange"));
}

const DEFAULT_SETTINGS = { density: "comfortable", emailDigest: true, assignAlerts: true, defaultFilter: "pending" };
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
  const [user, setUser] = useState(null);
  const [settings, setSettingsState] = useState(loadSettings);
  const parts = useHashParts();
  const setSettings = (patch) =>
    setSettingsState((s) => {
      const n = { ...s, ...patch };
      try { localStorage.setItem("tc.settings", JSON.stringify(n)); } catch { /* ignore */ }
      return n;
    });

  if (!user) {
    const landing = (h) => (!h || h === "#" || h === "#/") ? "#/submit" : h;
    return <Login onSignIn={(email) => { setUser({ email }); nav(landing(window.location.hash)); }} />;
  }

  const route = parts[0];
  const onReviews = route === "reviews";
  const detailId = onReviews ? parts[1] : null;
  const pending = FAKE_REVIEWS.filter((r) => r.status === "pending").length;

  return (
    <div className={`app ${settings.density === "compact" ? "compact" : ""}`}>
      <header className="topbar">
        <div className="seal">T</div>
        <b>Treasury Console</b>
        <span className="env">DEV · us-east-2</span>
        <UserMenu email={user.email} onNav={nav} onSignOut={() => setUser(null)} />
      </header>
      <nav className="tabs">
        <button className={route === "submit" ? "on" : ""} onClick={() => nav("#/submit")}>Submit Payment</button>
        <button className={onReviews ? "on" : ""} onClick={() => nav("#/reviews")}>
          Review Queue{pending > 0 && <span className="badge">{pending}</span>}
        </button>
      </nav>
      <main className="content">
        {route === "submit" && <Submit />}
        {onReviews && !detailId && <ReviewQueue defaultFilter={settings.defaultFilter} onOpen={(id) => nav(`#/reviews/${id}`)} />}
        {onReviews && detailId && <AuditDetail paymentId={detailId} onBack={() => nav("#/reviews")} />}
        {route === "profile" && <Profile email={user.email} />}
        {route === "settings" && <Settings settings={settings} onChange={setSettings} />}
      </main>
      <footer className="foot">
        <span>Treasury Console · v1.3.0</span>
        <span>DEV · us-east-2</span>
        <span>Records are immutably audited — S3 Object Lock (COMPLIANCE)</span>
      </footer>
    </div>
  );
}
