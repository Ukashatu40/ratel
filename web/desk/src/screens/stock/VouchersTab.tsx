import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, type Tone } from "../../components/ui";
import { ApiError, newIdempotencyKey } from "../../lib/api";
import { formatCount, formatNaira, formatWAT } from "../../lib/format";
import { advanceBatch, getVoucherBatches, lockBatch, lockCard, lookupCard, printBatch, requestBatch } from "./api";
import { NEXT_BATCH_STEP, type VoucherBatch, type VoucherCard, type VoucherState } from "./types";

// Every voucher step is an admin's, and every one is recorded with who took it and why (docs/runbooks/voucher-batches.md).
const TONE: Record<VoucherState, Tone> = { requested: "blue", approved: "blue", sent_to_printer: "amber", in_stock: "green", on_sale: "green", expired: "grey", used: "grey", locked: "red" };
const LABEL: Record<VoucherState, string> = { requested: "requested", approved: "approved", sent_to_printer: "printed", in_stock: "in stock", on_sale: "on sale", expired: "expired", used: "used", locked: "locked" };
const StateBadge = ({ state }: { state: VoucherState }) => <Badge tone={TONE[state]}>{LABEL[state]}</Badge>;
const message = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong");

function RequestForm({ values, maxCards, onDone }: { values: number[]; maxCards: number; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [face, setFace] = useState(String(values[0] ?? ""));
  const [count, setCount] = useState("24");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [key] = useState(newIdempotencyKey);
  const request = useMutation({
    mutationFn: (v: { faceValueKobo: number; cardCount: number; reason: string }) => requestBatch(v, key),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["stock"] }); onDone(); },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const n = /^\d+$/.test(count.trim()) ? Number(count) : 0;
    if (n < 1 || n > maxCards) return setError(`Enter between 1 and ${maxCards} cards (24 fit on a page)`);
    if (reason.trim().length < 3) return setError("Say what the batch is for");
    setError("");
    request.mutate({ faceValueKobo: Number(face), cardCount: n, reason: reason.trim() });
  };
  return (
    <form className="card" onSubmit={submit} noValidate>
      <h3>Request a voucher batch</h3>
      <div className="stock-form">
        <div className="field">
          <label htmlFor="v-face">Face value</label>
          <select id="v-face" className="input" value={face} onChange={(e) => setFace(e.target.value)}>
            {values.map((v) => <option key={v} value={v}>{formatNaira(v)}</option>)}
          </select>
        </div>
        <div className="field"><label htmlFor="v-count">Number of cards</label><input id="v-count" className="input" inputMode="numeric" value={count} onChange={(e) => setCount(e.target.value)} /></div>
      </div>
      <div className="field"><label htmlFor="v-reason">What it is for (saved in the history)</label><input id="v-reason" className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Demo stock for the launch" /></div>
      {(error || request.isError) && <div className="alert alert--danger" style={{ marginBottom: 12 }}>{error || message(request.error)}</div>}
      <div className="stock-actions">
        <button type="button" className="btn btn--outline" onClick={onDone}>Cancel</button>
        <button type="submit" className="btn" disabled={request.isPending}>{request.isPending ? "Requesting..." : "Request batch"}</button>
      </div>
      <p className="muted stock-note">No card or PIN exists until the batch is approved and its sheet printed. The face values are set in Plans &amp; Bundles.</p>
    </form>
  );
}

// A confirm step, with a reason where the step needs one, for every action that changes a batch or a card.
function ActionDialog({ title, body, confirm, danger, needsReason, onConfirm, onClose }: {
  title: string; body: string; confirm: string; danger?: boolean; needsReason: boolean;
  onConfirm: (reason: string) => Promise<unknown>; onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState("");
  const run = useMutation({ mutationFn: () => onConfirm(reason.trim()), onSuccess: () => ref.current?.close() });
  useEffect(() => { ref.current?.showModal(); }, []);
  return (
    <dialog ref={ref} className="stock-dialog" onClose={onClose} aria-label={title}>
      <h3>{title}</h3>
      <p className="muted" style={{ margin: "6px 0 14px" }}>{body}</p>
      {needsReason && <div className="field"><label htmlFor="action-reason">Reason (required, saved in the history)</label><textarea id="action-reason" className="input" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus /></div>}
      {run.isError && <div className="alert alert--danger" style={{ marginBottom: 12 }}>{message(run.error)}</div>}
      <div className="stock-actions" style={{ justifyContent: "flex-end" }}>
        <button type="button" className="btn btn--outline" onClick={() => ref.current?.close()} disabled={run.isPending}>Cancel</button>
        <button type="button" className={danger ? "btn btn--danger" : "btn"} disabled={(needsReason && reason.trim().length < 3) || run.isPending} onClick={() => run.mutate()}>{run.isPending ? "Working..." : confirm}</button>
      </div>
    </dialog>
  );
}

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 60_000); // the sheet holds live PINs: drop the browser's copy soon after
}

type Pending = { batch: VoucherBatch; kind: "step" | "lock" } | null;

function BatchDialog({ pending, onClose }: { pending: NonNullable<Pending>; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [key] = useState(newIdempotencyKey);
  const { batch, kind } = pending;
  const done = () => void queryClient.invalidateQueries({ queryKey: ["stock"] });
  const step = NEXT_BATCH_STEP[batch.state];
  if (kind === "lock") {
    return <ActionDialog title={`Lock batch ${batch.name}?`} danger needsReason confirm="Lock batch" onClose={onClose}
      body="Every card of this batch that is not used is locked and can never be recharged. Use this for a lost or stolen sheet or box, or a sheet that never downloaded."
      onConfirm={async (reason) => { await lockBatch(batch.batchId, reason, key); done(); }} />;
  }
  if (step?.kind === "print") {
    return <ActionDialog title={`Print batch ${batch.name}?`} needsReason={false} confirm="Make cards and download PDF" onClose={onClose}
      body={`This makes ${formatCount(batch.cardCount)} cards and their PINs and downloads them once, as a PDF. The PINs cannot be shown again. Keep the file and the printed sheet locked away.`}
      onConfirm={async () => { download(await printBatch(batch.batchId, key), `ratelplus-vouchers-${batch.name}.pdf`); done(); }} />;
  }
  if (step?.kind === "advance") {
    const bodies = { approved: "Approving lets the sheet be printed.", in_stock: "Mark the printed cards as received in stock. They cannot be recharged yet.", on_sale: `From now on every card of this batch can be recharged (${formatNaira(batch.faceValueKobo)} each).` };
    return <ActionDialog title={`${step.label}: ${batch.name}`} needsReason confirm={step.label} onClose={onClose} body={bodies[step.to]}
      onConfirm={async (reason) => { await advanceBatch(batch.batchId, step.to, reason, key); done(); }} />;
  }
  return null;
}

function CardLookup() {
  const queryClient = useQueryClient();
  const [number, setNumber] = useState("");
  const [locking, setLocking] = useState(false);
  const [key] = useState(newIdempotencyKey);
  const find = useMutation({ mutationFn: (n: string) => lookupCard(n) });
  const card: VoucherCard | undefined = find.data;
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
          <div className="stock-kv"><span>Card number</span><span>•••• •••• •••• •••• {card.last4}</span></div>
          <div className="stock-kv"><span>Batch</span><span>{card.batch}</span></div>
          <div className="stock-kv"><span>Face value</span><span>{formatNaira(card.faceValueKobo)}</span></div>
          <div className="stock-kv"><span>State</span><StateBadge state={card.state} /></div>
          <div className="stock-kv"><span>Failed attempts this hour</span>{attempts}</div>
          {card.usedAt && <div className="stock-kv"><span>Recharged</span><span>{card.usedByMsisdn} on {formatWAT(card.usedAt)}</span></div>}
          <button type="button" className="btn btn--danger" style={{ width: "100%", margin: "14px 0 8px" }} disabled={!lockable} onClick={() => setLocking(true)}>Lock card</button>
          <p className="muted stock-note">PINs are stored hashed and are never shown.</p>
        </div>
      )}
      {locking && card && <ActionDialog title={`Lock card ending ${card.last4}?`} danger needsReason confirm="Lock card" onClose={() => { setLocking(false); find.mutate(digits); }}
        body="A locked card can never be recharged. Use this for a lost or stolen card."
        onConfirm={async (reason) => { await lockCard(card.voucherId, reason, key); void queryClient.invalidateQueries({ queryKey: ["stock"] }); }} />}
    </section>
  );
}

export function VouchersTab() {
  const [requesting, setRequesting] = useState(false);
  const [pending, setPending] = useState<Pending>(null);
  const batches = useQuery({ queryKey: ["stock", "voucher-batches"], queryFn: getVoucherBatches });
  return (
    <div className="stock-vouchers">
      <div className="stock-col">
        {requesting && batches.data ? <RequestForm values={batches.data.voucherValuesKobo} maxCards={batches.data.maxCards} onDone={() => setRequesting(false)} />
          : <div><button type="button" className="btn" disabled={!batches.data} onClick={() => setRequesting(true)}>Request voucher batch</button></div>}
        <section className="card stock-card">
          <h3>Voucher batches</h3>
          {batches.isError ? <div className="stock-message">Could not load batches. <button type="button" className="btn btn--sm" onClick={() => batches.refetch()}>Try again</button></div> : (
            <div style={{ overflowX: "auto" }}>
            <table className="data-table">
              <thead><tr><th>Batch</th><th>Face value</th><th>Cards</th><th>State</th><th style={{ textAlign: "right" }}>Actions</th></tr></thead>
              <tbody>
                {batches.isPending && <tr><td colSpan={5} className="muted">Loading...</td></tr>}
                {batches.data?.items.length === 0 && <tr><td colSpan={5} className="muted">No batches yet. Request one to start.</td></tr>}
                {batches.data?.items.map((b) => {
                  const step = NEXT_BATCH_STEP[b.state];
                  return (
                    <tr key={b.batchId}>
                      <td style={{ whiteSpace: "nowrap" }}><b>{b.name}</b><div className="muted" style={{ fontSize: 12 }} title={b.requestedAt ? `requested ${formatWAT(b.requestedAt)}` : undefined}>{b.requestedBy}</div></td>
                      <td style={{ whiteSpace: "nowrap" }}>{formatNaira(b.faceValueKobo)}</td>
                      <td style={{ whiteSpace: "nowrap" }}>{formatCount(b.cardCount)}{b.cardsUsed > 0 && <span className="muted"> ({formatCount(b.cardsUsed)} used)</span>}</td>
                      <td><StateBadge state={b.state} /></td>
                      <td>
                        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", whiteSpace: "nowrap" }}>
                          {step && <button type="button" className={step.kind === "print" ? "btn btn--sm" : "btn btn--outline btn--sm"} onClick={() => setPending({ batch: b, kind: "step" })}>{step.label}</button>}
                          {b.state !== "locked" && <button type="button" className="btn btn--outline btn--sm" aria-label={`Lock batch ${b.name}`} onClick={() => setPending({ batch: b, kind: "lock" })}>Lock</button>}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
          )}
        </section>
      </div>
      <CardLookup />
      {pending && <BatchDialog pending={pending} onClose={() => setPending(null)} />}
    </div>
  );
}
