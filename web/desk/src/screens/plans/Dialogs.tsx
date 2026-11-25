import { useEffect, useRef, useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { newIdempotencyKey } from "../../lib/api";
import { retireOffer, saveOffer } from "./api";
import type { BundleInput, Kind, PlanInput } from "./types";

// Native modal dialog: traps focus and closes on Escape.
function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return <dialog ref={ref} className="plans-dialog" onClose={onClose} aria-label={title}><h3>{title}</h3>{children}</dialog>;
}

function useRefresh(kind: Kind, id: string | null) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: [kind === "plan" ? "plans" : "bundles"] });
    if (id) void queryClient.invalidateQueries({ queryKey: ["offer-history", kind, id] });
    if (kind === "plan") void queryClient.invalidateQueries({ queryKey: ["plans", "on_sale"] }); // Sell SIM's list
  };
}

// The safety warning: edits never touch what customers already bought.
export function ConfirmSaveDialog({ kind, id, name, value, reason, onClose, onDone }: { kind: Kind; id: string; name: string; value: PlanInput | BundleInput; reason: string; onClose: () => void; onDone: () => void }) {
  const [key] = useState(newIdempotencyKey); // a new key for each confirmation
  const refresh = useRefresh(kind, id);
  const save = useMutation({ mutationFn: () => saveOffer(kind, id, value, key, reason), onSuccess: () => { refresh(); onDone(); } });
  const word = kind === "plan" ? "plan" : "bundle";
  return (
    <Modal title={`Save changes to ${name}?`} onClose={onClose}>
      <div className="alert alert--warn" style={{ margin: "12px 0 18px" }}>Saving publishes the changed {word} and retires this one. Customers who already bought it keep what they paid for.</div>
      {save.isError && <div className="alert alert--danger" style={{ marginBottom: 12 }}>{save.error.message}</div>}
      <div className="plans-dialog__actions">
        <button type="button" className="btn btn--outline" onClick={onClose} disabled={save.isPending}>Cancel</button>
        <button type="button" className="btn" onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? "Saving..." : "Save changes"}</button>
      </div>
    </Modal>
  );
}

export function RetireDialog({ kind, id, name, onClose, onDone }: { kind: Kind; id: string; name: string; onClose: () => void; onDone: () => void }) {
  const [key] = useState(newIdempotencyKey);
  const refresh = useRefresh(kind, id);
  const [reason, setReason] = useState("");
  const retire = useMutation({ mutationFn: () => retireOffer(kind, id, key, reason.trim()), onSuccess: () => { refresh(); onDone(); } });
  return (
    <Modal title={`Retire ${name}?`} onClose={onClose}>
      <p className="muted" style={{ margin: "8px 0 16px" }}>It will no longer be sold. Customers who already bought it keep it until it ends. A retired {kind} cannot be edited or put back on sale.</p>
      <div className="field" style={{ marginBottom: 14 }}>
        <label htmlFor="retire-reason">Reason (kept in the audit trail)</label>
        <input id="retire-reason" className="input" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} />
      </div>
      {retire.isError && <div className="alert alert--danger" style={{ marginBottom: 12 }}>{retire.error.message}</div>}
      <div className="plans-dialog__actions">
        <button type="button" className="btn btn--outline" onClick={onClose} disabled={retire.isPending}>Cancel</button>
        <button type="button" className="btn btn--danger" onClick={() => retire.mutate()} disabled={retire.isPending || !reason.trim()}>{retire.isPending ? "Retiring..." : `Retire ${kind}`}</button>
      </div>
    </Modal>
  );
}
