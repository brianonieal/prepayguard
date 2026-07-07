import Submit from "../screens/Submit.jsx";

// Submit is now an occasional action (the feeder is the real intake), so it lives in
// a modal opened from a header button rather than a full tab.
export default function SubmitModal({ onClose }) {
  return (
    <div className="modal-overlay" role="dialog" aria-label="Submit a payment" onClick={onClose}
      style={{ position: "fixed", inset: 0, background: "rgba(10,20,35,0.5)", zIndex: 100, overflowY: "auto" }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 900, margin: "36px auto", background: "#faf8f3", borderRadius: 8, boxShadow: "0 12px 40px rgba(0,0,0,0.35)" }}>
        <div style={{ display: "flex", justifyContent: "flex-end", padding: "10px 14px 0" }}>
          <button className="rowlink" aria-label="close" onClick={onClose}>✕ Close</button>
        </div>
        <Submit />
      </div>
    </div>
  );
}
