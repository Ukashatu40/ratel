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
export function ConfirmSaveDialog({ kind, id, name, value, onClose, onDone }: { kind: Kind; id: string; name: string; value: PlanInput | BundleInput; onClose: () => void; onDone: () => void }) {
  const [key] = useState(newIdempotencyKey); // a new key for each confirmation
  const refresh = useRefresh(kind, id);
  const save = useMutation({ mutationFn: () => saveOffer(kind, id, value, key), onSuccess: () => { refresh(); onDone(); } });
  const word = kind === "plan" ? "plan" : "bundle";
  return (
    <Modal title={`Save changes to ${name}?`} onClose={onClose}>
      <div className="alert alert--warn" style={{ margin: "12px 0 18px" }}>Modifying a {word} applies strictly to new purchases; existing active allowances remain unchanged.</div>
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
  const retire = useMutation({ mutationFn: () => retireOffer(kind, id, key), onSuccess: () => { refresh(); onDone(); } });
  return (
    <Modal title={`Retire ${name}?`} onClose={onClose}>
      <p className="muted" style={{ margin: "8px 0 16px" }}>It will no longer be sold. Customers who already bought it keep it until it ends. A retired {kind} cannot be edited or put back on sale.</p>
      {retire.isError && <div className="alert alert--danger" style={{ marginBottom: 12 }}>{retire.error.message}</div>}
      <div className="plans-dialog__actions">
        <button type="button" className="btn btn--outline" onClick={onClose} disabled={retire.isPending}>Cancel</button>
        <button type="button" className="btn btn--danger" onClick={() => retire.mutate()} disabled={retire.isPending}>{retire.isPending ? "Retiring..." : `Retire ${kind}`}</button>
      </div>
    </Modal>
  );
}
