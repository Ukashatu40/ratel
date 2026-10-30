import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { newIdempotencyKey } from "../../lib/api";
import { NEXT_ATTACH_NOTE } from "../../lib/messages";
import { suspendLine } from "./api";
import type { LineRow } from "./types";

// A suspension always needs a reason (it goes in the line's history).
export function SuspendDialog({ line, onClose }: { line: LineRow; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState("");
  const [key] = useState(newIdempotencyKey); // one key per confirmation, so a retry cannot suspend twice
  const queryClient = useQueryClient();
  const suspend = useMutation({
    mutationFn: () => suspendLine(line.imsi, reason.trim(), key),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["lines"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      onClose();
    },
  });

  useEffect(() => { dialog.current?.showModal(); }, []); // native modal: traps focus, Escape closes it

  return (
    <dialog ref={dialog} className="lines-dialog" onClose={onClose} aria-labelledby="suspend-title">
      <h3 id="suspend-title">Suspend {line.msisdn}?</h3>
      <p className="muted" style={{ margin: "6px 0 14px" }}>{line.customerName} will lose internet and calls.</p>
      <div className="field">
        <label htmlFor="suspend-reason">Reason (required, saved in the line's history)</label>
        <textarea id="suspend-reason" className="input" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
      </div>
      <div className="alert alert--warn">{NEXT_ATTACH_NOTE}</div>
      {suspend.isError && <div className="alert alert--danger" style={{ marginTop: 12 }}>{suspend.error.message}</div>}
      <div className="lines-dialog__actions">
        <button type="button" className="btn btn--outline" onClick={() => dialog.current?.close()} disabled={suspend.isPending}>Cancel</button>
        <button type="button" className="btn btn--danger" onClick={() => suspend.mutate()} disabled={reason.trim().length < 3 || suspend.isPending}>
          {suspend.isPending ? "Suspending..." : "Suspend line"}
        </button>
      </div>
    </dialog>
  );
}