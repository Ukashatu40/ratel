import { useEffect, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { newIdempotencyKey } from "../../lib/api";
import { formatWAT } from "../../lib/format";
import { getOfferHistory, saveOffer } from "./api";
import { ConfirmSaveDialog, RetireDialog } from "./Dialogs";
import { build, type Errors, type FormState } from "./form";
import { CHANNELS, type BundleInput, type Kind, type OfferStatus, type PlanInput } from "./types";

interface Props { kind: Kind; id: string | null; status: OfferStatus; initial: FormState; onClose: () => void }

function Field({ id, label, error, children, wide }: { id: string; label: string; error?: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={`field${wide ? " plans-wide" : ""}`}>
      <label htmlFor={id}>{label}</label>
      {children}
      {error && <span className="field__error">{error}</span>}
    </div>
  );
}

// The create / edit drawer. Saving an existing plan or bundle first shows the "new purchases only" warning.
export function OfferDrawer({ kind, id, status, initial, onClose }: Props) {
  const queryClient = useQueryClient();
  const panel = useRef<HTMLElement>(null);
  const [tab, setTab] = useState<"details" | "history">("details");
  const [form, setForm] = useState<FormState>(initial);
  const [errors, setErrors] = useState<Errors>({});
  const [confirm, setConfirm] = useState<PlanInput | BundleInput | null>(null);
  const [retiring, setRetiring] = useState(false);
  const [createKey] = useState(newIdempotencyKey); // one key for the create request, so a retry cannot create twice
  const readOnly = status === "retired";
  const word = kind === "plan" ? "plan" : "bundle";

  const history = useQuery({ queryKey: ["offer-history", kind, id], queryFn: () => getOfferHistory(kind, id as string), enabled: id !== null });
  const create = useMutation({
    mutationFn: (value: PlanInput | BundleInput) => saveOffer(kind, null, value, createKey),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: [kind === "plan" ? "plans" : "bundles"] }); onClose(); },
  });

  useEffect(() => {
    panel.current?.focus();
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape" && !document.querySelector("dialog[open]")) onClose(); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [onClose]);

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setForm({ ...form, [k]: v });
  const text = (k: "name" | "price" | "validity" | "dataGb" | "ul" | "dl" | "slowUl" | "slowDl") => ({ id: `f-${k}`, className: "input", value: form[k], disabled: readOnly, onChange: (e: { target: { value: string } }) => set(k, e.target.value) });
  const toggle = (ch: string) => set("channels", form.channels.includes(ch) ? form.channels.filter((c) => c !== ch) : [...form.channels, ch]);

  const submit = () => {
    const { errors: found, value } = build(kind, form);
    setErrors(found);
    if (!value) return;
    if (id === null) create.mutate(value); else setConfirm(value);
  };

  return (
    <aside className="plans-drawer" ref={panel} tabIndex={-1} aria-label={`${word} details`}>
      <div className="plans-drawer__head">
        <h3>{id === null ? `Create ${word}` : `Edit ${word}: ${initial.name}`}</h3>
        <button type="button" className="plans-drawer__close" onClick={onClose} aria-label="Close">✕</button>
      </div>

      {id !== null && (
        <div className="plans-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={tab === "details"} className={tab === "details" ? "on" : ""} onClick={() => setTab("details")}>Details</button>
          <button type="button" role="tab" aria-selected={tab === "history"} className={tab === "history" ? "on" : ""} onClick={() => setTab("history")}>History</button>
        </div>
      )}

      {tab === "details" && (
        <>
          {readOnly && <div className="alert alert--warn" style={{ marginBottom: 14 }}>This {word} is retired, so it can no longer be edited.</div>}
          <div className="plans-form">
            <Field id="f-name" label="Name" error={errors.name} wide><input {...text("name")} /></Field>
            <Field id="f-price" label="Price (₦)" error={errors.price}><input {...text("price")} inputMode="decimal" /></Field>
            <Field id="f-validity" label="Validity (days)" error={errors.validity}><input {...text("validity")} inputMode="numeric" /></Field>
            <Field id="f-dataGb" label="Data (GB)" error={errors.dataGb}><input {...text("dataGb")} inputMode="decimal" /></Field>
            <div className="field">
              <label>Channels</label>
              <div className="plans-channels">
                {CHANNELS.map((ch) => (
                  <label key={ch}><input type="checkbox" checked={form.channels.includes(ch)} disabled={readOnly} onChange={() => toggle(ch)} /> {ch}</label>
                ))}
              </div>
              {errors.channels && <span className="field__error">{errors.channels}</span>}
            </div>
            {kind === "plan" && (
              <>
                <Field id="f-ul" label="Upload (Mbps)" error={errors.ul}><input {...text("ul")} inputMode="decimal" /></Field>
                <Field id="f-dl" label="Download (Mbps)" error={errors.dl}><input {...text("dl")} inputMode="decimal" /></Field>
                <Field id="f-exhaustion" label="On exhaustion" wide>
                  <select id="f-exhaustion" className="input" value={form.exhaustion} disabled={readOnly} onChange={(e) => set("exhaustion", e.target.value as "slow" | "stop")}>
                    <option value="slow">Slow down (calls keep working)</option>
                    <option value="stop">Stop internet (calls keep working)</option>
                  </select>
                </Field>
                {form.exhaustion === "slow" && (
                  <>
                    <Field id="f-slowUl" label="Slow upload (Mbps)" error={errors.slowUl}><input {...text("slowUl")} inputMode="decimal" /></Field>
                    <Field id="f-slowDl" label="Slow download (Mbps)" error={errors.slowDl}><input {...text("slowDl")} inputMode="decimal" /></Field>
                  </>
                )}
              </>
            )}
          </div>
          {create.isError && <div className="alert alert--danger" style={{ marginBottom: 12 }}>{create.error.message}</div>}
          {!readOnly && (
            <div className="plans-actions">
              <button type="button" className="btn" onClick={submit} disabled={create.isPending}>{id === null ? (create.isPending ? "Creating..." : `Create ${word}`) : "Save changes"}</button>
              {id !== null && <button type="button" className="btn btn--outline" onClick={() => setRetiring(true)}>Retire {word}</button>}
            </div>
          )}
        </>
      )}

      {tab === "history" && id !== null && (
        <>
          {history.isPending && <p className="muted">Loading...</p>}
          {history.isError && <div className="alert alert--danger">Could not load the history.</div>}
          <ol className="plans-timeline">
            {history.data?.map((e) => (
              <li key={`${e.at}-${e.action}`}><b>{e.action}</b> by {e.actor}<small>{formatWAT(e.at)}{e.detail ? ` | ${e.detail}` : ""}</small></li>
            ))}
          </ol>
        </>
      )}

      {confirm && id !== null && <ConfirmSaveDialog kind={kind} id={id} name={initial.name} value={confirm} onClose={() => setConfirm(null)} onDone={() => { setConfirm(null); onClose(); }} />}
      {retiring && id !== null && <RetireDialog kind={kind} id={id} name={initial.name} onClose={() => setRetiring(false)} onDone={() => { setRetiring(false); onClose(); }} />}
    </aside>
  );
}
