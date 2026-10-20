import { useDeferredValue, useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Badge, type Tone } from "../../components/ui";
import { maskNin } from "../../lib/format";
import { createCustomer, searchCustomers } from "./api";
import type { Customer, KycStatus, NewCustomer } from "./types";

const KYC_TONE: Record<KycStatus, Tone> = { verified: "green", pending: "amber", rejected: "red" };
const KycBadge = ({ status }: { status: KycStatus }) => <Badge tone={KYC_TONE[status]}>{status[0].toUpperCase() + status.slice(1)}</Badge>;

// The customer card shown at the top of every step once someone is chosen.
export function CustomerCard({ customer, onChange }: { customer: Customer; onChange?: () => void }) {
  return (
    <div className="card sell-customer">
      <div>
        <h3>Customer</h3>
        <div className="sell-customer__name">{customer.name}</div>
        <div className="muted">{customer.idType} {maskNin(customer.idNumber)} &nbsp;|&nbsp; {customer.phone} &nbsp;|&nbsp; {customer.email || "no email"}</div>
        <div className="muted">{customer.address}</div>
        {onChange && <button type="button" className="btn btn--outline btn--sm" style={{ marginTop: 10 }} onClick={onChange}>Change customer</button>}
      </div>
      <div className="sell-customer__kyc">
        <div className="muted">KYC status</div>
        <KycBadge status={customer.kycStatus} />
        <div className="muted" style={{ marginTop: 6 }}>Blocked: {customer.blocked ? "yes" : "no"}</div>
      </div>
    </div>
  );
}

const EMPTY = { name: "", phone: "", email: "", idNumber: "", address: "" };

function NewCustomerForm({ onCreated, onCancel }: { onCreated: (c: Customer) => void; onCancel: () => void }) {
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState<Partial<Record<keyof typeof EMPTY, string>>>({});
  const create = useMutation({ mutationFn: (input: NewCustomer) => createCustomer(input), onSuccess: onCreated });
  const set = (k: keyof typeof EMPTY) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const next: typeof errors = {};
    if (!form.name.trim()) next.name = "Enter the customer's full name";
    if (form.phone.replace(/\D/g, "").length < 10) next.phone = "Enter a valid phone number";
    if (!/^\d{11}$/.test(form.idNumber)) next.idNumber = "A NIN has 11 digits"; // NIN is captured at registration
    if (!form.address.trim()) next.address = "Enter the customer's address";
    setErrors(next);
    if (Object.keys(next).length === 0) create.mutate({ ...form, name: form.name.trim(), idType: "NIN" });
  };

  const field = (k: keyof typeof EMPTY, label: string, props: { placeholder?: string; inputMode?: "numeric" | "tel" } = {}) => (
    <div className="field">
      <label htmlFor={`cust-${k}`}>{label}</label>
      <input id={`cust-${k}`} className="input" value={form[k]} onChange={set(k)} {...props} />
      {errors[k] && <span className="field__error">{errors[k]}</span>}
    </div>
  );

  return (
    <form className="card" onSubmit={submit} noValidate>
      <h3>Register a new customer</h3>
      <div className="sell-form">
        {field("name", "Full name")}
        {field("phone", "Phone number", { inputMode: "tel", placeholder: "+234 ..." })}
        {field("idNumber", "NIN (11 digits)", { inputMode: "numeric" })}
        {field("email", "Email (optional)")}
      </div>
      {field("address", "Address")}
      {create.isError && <div className="alert alert--danger" style={{ marginBottom: 12 }}>Could not save the customer. Try again.</div>}
      <div className="sell-actions">
        <button type="button" className="btn btn--outline" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn" disabled={create.isPending}>{create.isPending ? "Saving..." : "Save and select customer"}</button>
      </div>
      <p className="muted" style={{ marginTop: 10, fontSize: 13 }}>New customers start with KYC pending. A line cannot be activated until KYC is verified.</p>
    </form>
  );
}

export function CustomerStep({ onSelect }: { onSelect: (c: Customer) => void }) {
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const term = useDeferredValue(q.trim());
  const { data, isFetching } = useQuery({ queryKey: ["customers", term], queryFn: () => searchCustomers(term), enabled: term.length >= 2 });

  if (creating) return <NewCustomerForm onCreated={onSelect} onCancel={() => setCreating(false)} />;
  return (
    <div className="card">
      <div className="sell-split">
        <h3>Find the customer</h3>
        <button type="button" className="btn btn--outline btn--sm" onClick={() => setCreating(true)}>Register a new customer</button>
      </div>
      <input className="input" autoFocus placeholder="Search by name, phone number or NIN" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search customers" />
      <div className="sell-results" aria-live="polite">
        {term.length < 2 && <p className="muted">Type at least 2 characters.</p>}
        {term.length >= 2 && isFetching && !data && <p className="muted">Searching...</p>}
        {term.length >= 2 && data?.length === 0 && <p className="muted">No customer found. Use "Register a new customer".</p>}
        {data?.map((c) => (
          <button type="button" key={c.id} className="sell-result" onClick={() => onSelect(c)}>
            <span><b>{c.name}</b><br /><span className="muted">{c.phone} &nbsp;|&nbsp; {c.idType} {maskNin(c.idNumber)}</span></span>
            <span className="sell-result__tags"><KycBadge status={c.kycStatus} />{c.blocked && <Badge tone="red">Blocked</Badge>}</span>
          </button>
        ))}
      </div>
    </div>
  );
}