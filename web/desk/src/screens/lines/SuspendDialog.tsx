import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { newIdempotencyKey } from "../../lib/api";
import { NEXT_ATTACH_NOTE } from "../../lib/messages";
import { suspendLine } from "./api";
import { CARE_REASONS, CARE_REASON_LABEL, type CareReason, type LineRow } from "./types";

// A suspension always needs a reason (PRD decision 9: fixed list + free text).
// The wire field for the free text is "reason_text" (SuspendLineRequest in contracts/openapi.yaml).
export function SuspendDialog({ line, onClose }: { line: LineRow; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState<CareReason>("customer_request");
  const [reasonText, setReasonText] = useState("");
  const [key] = useState(newIdempotencyKey);
  const queryClient = useQueryClient();
  const suspend = useMutation({
    mutationFn: () => suspendLine(line.imsi, { reason, reason_text: reasonText.trim() }, key),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["lines"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      onClose();
    },
  });

  useEffect(() => { dialog.current?.showModal(); }, []);

  return (
    <dialog ref={dialog} className="lines-dialog" onClose={onClose} aria-labelledby="suspend-title">
      <h3 id="suspend-title">Suspend {line.msisdn}?</h3>
      <p className="muted" style={{ margin: "6px 0 14px" }}>{line.customerName} will lose internet and calls.</p>
      <div className="field">
        <label htmlFor="suspend-reason">Reason</label>
        <select id="suspend-reason" className="input" value={reason} onChange={(e) => setReason(e.target.value as CareReason)}>
          {CARE_REASONS.map((r) => <option key={r} value={r}>{CARE_REASON_LABEL[r]}</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor="suspend-reason-text">Additional note (optional, saved in the line's history)</label>
        <textarea id="suspend-reason-text" className="input" rows={2} value={reasonText} onChange={(e) => setReasonText(e.target.value)} />
      </div>
      <div className="alert alert--warn">{NEXT_ATTACH_NOTE}</div>
      {suspend.isError && <div className="alert alert--danger" style={{ marginTop: 12 }}>{suspend.error.message}</div>}
      <div className="lines-dialog__actions">
        <button type="button" className="btn btn--outline" onClick={() => dialog.current?.close()} disabled={suspend.isPending}>Cancel</button>
        <button type="button" className="btn btn--danger" onClick={() => suspend.mutate()} disabled={suspend.isPending}>
          {suspend.isPending ? "Suspending..." : "Suspend line"}
        </button>
      </div>
    </dialog>
  );
}
