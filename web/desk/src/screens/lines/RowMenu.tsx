import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { NEXT_ATTACH_NOTE } from "../../lib/messages";
import type { LineRow } from "./types";

// The navy "Actions" button with its dropdown: View Details, Top-Up, Suspend.
export function RowMenu({ line, onSuspend }: { line: LineRow; onSuspend: (line: LineRow) => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const outside = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", outside); document.removeEventListener("keydown", escape); };
  }, [open]);

  // Only active and out-of-data lines can be suspended (from the line state machine).
  const canSuspend = line.state === "active" || line.state === "out_of_data";
  return (
    <div className="lines-menu" ref={box}>
      <button type="button" className="btn btn--sm" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>Actions ▾</button>
      {open && (
        <div className="lines-menu__list" role="menu">
          <Link role="menuitem" to={`/lines/${line.imsi}`}>View Details</Link>
          <Link role="menuitem" to={`/lines/${line.imsi}?action=topup`}>Top-Up</Link>
          <button type="button" role="menuitem" className="lines-menu__danger" disabled={!canSuspend} onClick={() => { setOpen(false); onSuspend(line); }}>Suspend</button>
          <div className="alert alert--warn lines-menu__note">{NEXT_ATTACH_NOTE}</div>
        </div>
      )}
    </div>
  );
}