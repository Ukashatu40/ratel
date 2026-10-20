import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, type Tone } from "../../components/ui";
import { ApiError, newIdempotencyKey } from "../../lib/api";
import { formatCount, formatNaira, formatWAT } from "../../lib/format";
import { advanceBatch, getVoucherBatches, lockCard, lookupCard, requestBatch } from "./api";
import { NEXT_BATCH_STEP, type VoucherCard, type VoucherState } from "./types";

const TONE: Record<VoucherState, Tone> = { requested: "blue", approved: "blue", sent_to_printer: "amber", in_stock: "green", on_sale: "green", expired: "grey", used: "grey", locked: "amber" };
const StateBadge = ({ state }: { state: VoucherState }) => <Badge tone={TONE[state]}>{state}</Badge>;

function RequestForm({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const [face, setFace] = useState("");
  const [count, setCount] = useState("");
  const [error, setError] = useState("");
  const [key] = useState(newIdempotencyKey);
  const request = useMutation({
    mutationFn: (v: { faceValueKobo: number; cardCount: number }) => requestBatch(v, key),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["stock"] }); onDone(); },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const kobo = /^\d+(\.\d{1,2})?$/.test(face.trim()) ? Math.round(Number(face) * 100) : 0; // whole kobo, never a decimal
    const n = /^\d+$/.test(count.trim()) ? Number(count) : 0;
    if (kobo <= 0) return setError("Enter the face value in naira, for example 1000");
    if (n < 1 || n > 10000) return setError("Enter between 1 and 10,000 cards");
    setError("");
    request.mutate({ faceValueKobo: kobo, cardCount: n });
  };
  return (
    <form className="card" onSubmit={submit} noValidate>
      <h3>Request a voucher batch</h3>
      <div className="stock-form">
        <div className="field"><label htmlFor="v-face">Face value (₦)</label><input id="v-face" className="input" inputMode="decimal" value={face} onChange={(e) => setFace(e.target.value)} /></div>
        <div className="field"><label htmlFor="v-count">Number of cards</label><input id="v-count" className="input" inputMode="numeric" value={count} onChange={(e) => setCount(e.target.value)} /></div>
      </div>
      {(error || request.isError) && <div className="alert alert--danger" style={{ marginBottom: 12 }}>{error || (request.error as Error).message}</div>}
      <div className="stock-actions">
        <button type="button" className="btn btn--outline" onClick={onDone}>Cancel</button>
        <button type="submit" className="btn" disabled={request.isPending}>{request.isPending ? "Requesting..." : "Request batch"}</button>
      </div>
      <p className="muted stock-note">Card numbers and PINs are made by the server. PINs are stored hashed and are never shown.</p>
    </form>
  );
}

function LockDialog({ card, onClose }: { card: VoucherCard; onClose: () => void }) {
  const queryClient = useQueryClient();
  const ref = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState("");
  const [key] = useState(newIdempotencyKey);
  const lock = useMutation({
    mutationFn: () => lockCard(card.voucherId, reason.trim(), key),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["stock"] }); onClose(); },
  });
  useEffect(() => { ref.current?.showModal(); }, []);
  return (
    <dialog ref={ref} className="stock-dialog" onClose={onClose} aria-label="Lock card">
      <h3>Lock card {card.maskedNumber}?</h3>
      <p className="muted" style={{ margin: "6px 0 14px" }}>A locked card cannot be redeemed. Use this for lost or stolen cards.</p>
      <div className="field"><label htmlFor="lock-reason">Reason (required, saved in the history)</label><textarea id="lock-reason" className="input" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus /></div>
      {lock.isError && <div className="alert alert--danger" style={{ marginBottom: 12 }}>{lock.error.message}</div>}
      <div className="stock-actions" style={{ justifyContent: "flex-end" }}>
        <button type="button" className="btn btn--outline" onClick={() => ref.current?.close()} disabled={lock.isPending}>Cancel</button>
        <button type="button" className="btn btn--danger" disabled={reason.trim().length < 3 || lock.isPending} onClick={() => lock.mutate()}>{lock.isPending ? "Locking..." : "Lock card"}</button>
      </div>
    </dialog>
  );
}

function CardLookup() {
  const [number, setNumber] = useState("");
  const [locking, setLocking] = useState(false);
  const find = useMutation({ mutationFn: (n: string) => lookupCard(n) });
  const card = find.data;
  const digits = number.replace(/\D/g, "");
  const attempts = card ? (card.failedAttempts >= card.maxAttempts ? <Badge tone="red">{card.failedAttempts} of {card.maxAttempts} (locked out)</Badge> : <Badge tone={card.failedAttempts >= 3 ? "amber" : "grey"}>{card.failedAttempts} of {card.maxAttempts} max</Badge>) : null;
  const lockable = card && card.state !== "used" && card.state !== "expired" && card.state !== "locked";
  return (
    <section className="card">
      <h3>Look up a card</h3>
      <form onSubmit={(e) => { e.preventDefault(); if (digits.length === 20) find.mutate(digits); }}>
        <div className="field"><label htmlFor="card-number">Card number (20 digits)</label><input id="card-number" className="input" inputMode="numeric" value={number} onChange={(e) => { setNumber(e.target.value); find.reset(); }} placeholder="1000 0000 0000 0000 4821" /></div>
        <button type="submit" className="btn btn--outline" disabled={digits.length !== 20 || find.isPending}>{find.isPending ? "Looking up..." : "Look up"}</button>
      </form>
      {find.isError && <div className="alert alert--danger" style={{ marginTop: 12 }}>{find.error instanceof ApiError && find.error.status === 404 ? "No voucher with that card number." : find.error.message}</div>}
      {card && (
        <div style={{ marginTop: 14 }}>
          <div className="stock-kv"><span>Card number</span><span>{card.maskedNumber}</span></div>
          <div className="stock-kv"><span>Batch</span><span>{card.batchId}</span></div>
          <div className="stock-kv"><span>Face value</span><span>{formatNaira(card.faceValueKobo)}</span></div>
          <div className="stock-kv"><span>State</span><StateBadge state={card.state} /></div>
          <div className="stock-kv"><span>Luhn check</span>{card.checkDigitValid ? <Badge tone="green">Valid</Badge> : <Badge tone="red">Invalid</Badge>}</div>
          <div className="stock-kv"><span>Failed attempts this hour</span>{attempts}</div>
          {card.redeemedAt && <div className="stock-kv"><span>Redeemed</span><span>{card.redeemedBy} on {formatWAT(card.redeemedAt)}</span></div>}
          <button type="button" className="btn btn--danger" style={{ width: "100%", margin: "14px 0 8px" }} disabled={!lockable} onClick={() => setLocking(true)}>Lock card</button>
          <p className="muted stock-note">PINs are stored hashed and never shown.</p>
        </div>
      )}
      {locking && card && <LockDialog card={card} onClose={() => { setLocking(false); find.mutate(digits); }} />}
    </section>
  );
}

export function VouchersTab() {
  const queryClient = useQueryClient();
  const [requesting, setRequesting] = useState(false);
  const batches = useQuery({ queryKey: ["stock", "voucher-batches"], queryFn: getVoucherBatches });
  const advance = useMutation({
    mutationFn: (batchId: string) => advanceBatch(batchId, newIdempotencyKey()),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["stock"] }),
  });
  return (
    <div className="stock-vouchers">
      <div className="stock-col">
        {requesting ? <RequestForm onDone={() => setRequesting(false)} /> : <div><button type="button" className="btn" onClick={() => setRequesting(true)}>Request voucher batch</button></div>}
        <section className="card stock-card">
          <h3>Voucher batches</h3>
          {advance.isError && <div className="alert alert--danger" style={{ margin: "0 20px 10px" }}>{advance.error.message}</div>}
          {batches.isError ? <div className="stock-message">Could not load batches. <button type="button" className="btn btn--sm" onClick={() => batches.refetch()}>Try again</button></div> : (
            <table className="data-table">
              <thead><tr><th>Batch</th><th>Face value</th><th>Cards</th><th>State</th><th>Created by</th><th>Next step</th></tr></thead>
              <tbody>
                {batches.isPending && <tr><td colSpan={6} className="muted">Loading...</td></tr>}
                {batches.data?.map((b) => {
                  const step = NEXT_BATCH_STEP[b.state];
                  return (
                    <tr key={b.batchId}>
                      <td><b>{b.batchId}</b></td><td>{formatNaira(b.faceValueKobo)}</td><td>{formatCount(b.cardCount)}</td><td><StateBadge state={b.state} /></td><td>{b.createdBy}</td>
                      <td>{step ? <button type="button" className="btn btn--outline btn--sm" disabled={advance.isPending} onClick={() => advance.mutate(b.batchId)}>{step.label}</button> : <span className="muted">-</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      </div>
      <CardLookup />
    </div>
  );
}
