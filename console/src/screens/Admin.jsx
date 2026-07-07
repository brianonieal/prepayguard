import { useState } from "react";
import ReferenceData from "./ReferenceData.jsx";
import Feed from "./Feed.jsx";

// One admin surface instead of two loose pages. The watchlist (Reference data) and
// the automated payment feed (Feed builder) live here as sub-sections. Each child
// screen brings its own .body, so the header wrapper stops its padding at the tabs.
export default function Admin({ initial = "reference" }) {
  const [tab, setTab] = useState(initial === "feed" ? "feed" : "reference");
  return (
    <>
      <div className="body" style={{ paddingBottom: 0 }}>
        <h2>Admin</h2>
        <div className="sub" style={{ marginBottom: 12 }}>
          Manage the screening watchlist and the automated payment feed.
        </div>
        <div className="subtabs">
          <button className={`chip ${tab === "reference" ? "on" : ""}`} onClick={() => setTab("reference")}>Reference data</button>
          <button className={`chip ${tab === "feed" ? "on" : ""}`} onClick={() => setTab("feed")}>Feed builder</button>
        </div>
      </div>
      {tab === "reference" ? <ReferenceData /> : <Feed />}
    </>
  );
}
