import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { NEXT_ATTACH_NOTE } from "../../lib/messages";
import type { CareKind, LineRow } from "./types";

// The navy "Actions" button with its dropdown: View Details, Top-Up, and Suspend or Reinstate. (Terminate is on the line page.)
export function RowMenu({ line, onAct }: { line: LineRow; onAct: (kind: CareKind, line: LineRow) => void }) {
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

  // Only active and out-of-data lines can be suspended, and only a suspended one reinstated (the line state machine).
  const canSuspend = line.state === "active" || line.state === "out_of_data";
  const canReinstate = line.state === "suspended";
  return (
    <div className="lines-menu" ref={box}>
      <button type="button" className="btn btn--sm" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>Actions ▾</button>
      {open && (
        <div className="lines-menu__list" role="menu">
          <Link role="menuitem" to={`/lines/${line.lineId}`}>View Details</Link>
          <Link role="menuitem" to={`/lines/${line.lineId}?action=topup`}>Top-Up</Link>
          {canReinstate
            ? <button type="button" role="menuitem" onClick={() => { setOpen(false); onAct("reinstate", line); }}>Reinstate</button>
            : <button type="button" role="menuitem" className="lines-menu__danger" disabled={!canSuspend} onClick={() => { setOpen(false); onAct("suspend", line); }}>Suspend</button>}
          <div className="alert alert--warn lines-menu__note">{NEXT_ATTACH_NOTE}</div>
        </div>
      )}
    </div>
  );
}