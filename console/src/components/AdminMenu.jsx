import { useEffect, useRef, useState } from "react";

// Admin-only config grouped under one nav dropdown so the top bar stays clean.
const ITEMS = [
  ["#/reference", "Reference Data"],
  ["#/feed", "Feed"],
  ["#/settings", "Demo controls"],
];

export default function AdminMenu({ route, onNav }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const active = ["reference", "feed", "settings"].includes(route);

  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button className={active ? "on" : ""} aria-haspopup="true" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        Admin ▾
      </button>
      {open && (
        <div role="menu" style={{
          position: "absolute", top: "100%", left: 0, zIndex: 60, minWidth: 170,
          background: "#0f2233", borderRadius: 6, boxShadow: "0 6px 18px rgba(0,0,0,0.35)", padding: 4,
        }}>
          {ITEMS.map(([hash, label]) => (
            <button key={hash} role="menuitem"
              style={{ display: "block", width: "100%", textAlign: "left", padding: "8px 12px", background: "none", border: 0, color: "#dfe7ef", cursor: "pointer" }}
              onClick={() => { onNav(hash); setOpen(false); }}>
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
