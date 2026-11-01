import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { keyFor, type KeySlot } from "../../lib/api";
import { formatMsisdn } from "../../lib/format";
import { NEXT_ATTACH_NOTE } from "../../lib/messages";
import { careAction } from "./api";
import { CARE_REASONS, CARE_REASON_LABEL, REASON_TEXT_MAX, type CareKind, type CareReason, type LineRow } from "./types";

// Suspend, reinstate and terminate are the same screen: every care action carries a reason from a fixed list plus
// optional free text (PRD decision 9), and is one call with its own Idempotency-Key.
const COPY: Record<CareKind, { title: string; blurb: (who: string) => string; confirm: string; busy: string; danger: boolean; attach: boolean }> = {
  suspend: { title: "Suspend", blurb: (who) => `${who} will lose internet and calls.`, confirm: "Suspend line", busy: "Suspending...", danger: true, attach: true },
  reinstate: { title: "Reinstate", blurb: (who) => `${who} gets internet and calls back, in the state the line had before it was suspended.`, confirm: "Reinstate line", busy: "Reinstating...", danger: false, attach: true },
  terminate: { title: "Terminate", blurb: (who) => `This is final. The SIM is retired and ${who}'s line cannot be used again.`, confirm: "Terminate line", busy: "Terminating...", danger: true, attach: false },
};

export function CareDialog({ kind, line, onClose }: { kind: CareKind; line: Pick<LineRow, "lineId" | "msisdn" | "customerName">; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState<CareReason>("customer_request");
  const [reasonText, setReasonText] = useState("");
  const slot = useRef<KeySlot>({ signature: null, key: null }); // a retry of the same action reuses its key
  const queryClient = useQueryClient();
  const copy = COPY[kind];
  const act = useMutation({
    mutationFn: () => {
      const payload = { reason, reasonText };
      return careAction(kind, line.lineId, payload, keyFor(slot.current, JSON.stringify(payload)));
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["lines"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["line", String(line.lineId)] });
      onClose();
    },
  });

  useEffect(() => { dialog.current?.showModal(); }, []);

  return (
    <dialog ref={dialog} className="lines-dialog" onClose={onClose} aria-labelledby="care-title">
      <h3 id="care-title">{copy.title} {formatMsisdn(line.msisdn)}?</h3>
      <p className="muted" style={{ margin: "6px 0 14px" }}>{copy.blurb(line.customerName)}</p>
      <div className="field">
        <label htmlFor="care-reason">Reason</label>
        <select id="care-reason" className="input" value={reason} onChange={(e) => setReason(e.target.value as CareReason)}>
          {CARE_REASONS.map((r) => <option key={r} value={r}>{CARE_REASON_LABEL[r]}</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor="care-reason-text">Additional note (optional, saved in the line's history)</label>
        <textarea id="care-reason-text" className="input" rows={2} maxLength={REASON_TEXT_MAX} value={reasonText} onChange={(e) => setReasonText(e.target.value)} />
      </div>
      {copy.attach && <div className="alert alert--warn">{NEXT_ATTACH_NOTE}</div>}
      {act.isError && <div className="alert alert--danger" role="alert" style={{ marginTop: 12 }}>{act.error.message}</div>}
      <div className="lines-dialog__actions">
        <button type="button" className="btn btn--outline" onClick={() => dialog.current?.close()} disabled={act.isPending}>Cancel</button>
        <button type="button" className={`btn${copy.danger ? " btn--danger" : ""}`} onClick={() => act.mutate()} disabled={act.isPending}>
          {act.isPending ? copy.busy : copy.confirm}
        </button>
      </div>
    </dialog>
  );
}
