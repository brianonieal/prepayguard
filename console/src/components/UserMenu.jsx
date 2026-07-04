import { useEffect, useRef, useState } from "react";

export default function UserMenu({ email, onNav, onSignOut }) {
  const [open, setOpen] = useState(false);
  const ref = useRef();

  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const go = (hash) => { setOpen(false); onNav(hash); };

  return (
    <div className="usermenu" ref={ref}>
      <button className="user" data-testid="user-menu-btn" onClick={() => setOpen((o) => !o)}>
        {email} ▾
      </button>
      {open && (
        <div className="menu">
          <button onClick={() => go("#/profile")}>Profile</button>
          <button onClick={() => go("#/settings")}>Settings</button>
          <div className="menu-sep" />
          <button className="danger" onClick={() => { setOpen(false); onSignOut(); }}>Sign out</button>
        </div>
      )}
    </div>
  );
}
