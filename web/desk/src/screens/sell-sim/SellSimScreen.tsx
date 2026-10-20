import { useState } from "react";
import { Link } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { newIdempotencyKey } from "../../lib/api";
import { formatNaira, formatWAT } from "../../lib/format";
import { activateLine } from "./api";
import { CustomerCard, CustomerStep } from "./CustomerStep";
import { OrderSummary } from "./OrderSummary";
import { totalKobo } from "./pricing";
import { PlanStep } from "./PlanStep";
import { SimNumberStep } from "./SimNumberStep";
import { Stepper } from "./Stepper";
import type { Customer, FreeSim, Plan } from "./types";
import "./SellSimScreen.css";

const CONTINUE = ["Continue", "Continue", "Continue to review", "Activate line"];
const KYC_MESSAGE = "A line cannot be activated until KYC is verified.";

export default function SellSimScreen() {
  const queryClient = useQueryClient();
  const [step, setStep] = useState(0);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [sim, setSim] = useState<FreeSim | null>(null);
  const [msisdn, setMsisdn] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [orderKey, setOrderKey] = useState(newIdempotencyKey); // one key per sale; a retry reuses it

  const activate = useMutation({
    mutationFn: () => activateLine({ customerId: customer!.id, iccid: sim!.iccid, msisdn, planId: plan!.planId }, orderKey),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["lines"] });
    },
  });

  const kycVerified = customer?.kycStatus === "verified";
  const blocked = customer?.blocked ?? false;
  // KYC hard gate: from the plan step onward the button stays disabled until the customer is verified.
  const canContinue = [!!customer && !blocked, !!sim && !!msisdn, !!plan && kycVerified && !blocked, !!plan && kycVerified && !blocked][step];

  const reset = () => {
    setStep(0); setCustomer(null); setSim(null); setMsisdn(""); setPlan(null);
    activate.reset();
    setOrderKey(newIdempotencyKey());
  };
  const next = () => (step < 3 ? setStep(step + 1) : activate.mutate());

  if (activate.isSuccess) {
    const r = activate.data;
    return (
      <div className="sell">
        <h1>Line activated</h1>
        <div className="card sell-done">
          <h3>{r.msisdn} is ready</h3>
          <div className="sell-kv"><span>Customer</span><span>{customer?.name}</span></div>
          <div className="sell-kv"><span>Plan</span><span>{r.planName}</span></div>
          <div className="sell-kv"><span>Plan ends</span><span>{formatWAT(r.expiresAt)}</span></div>
          <div className="sell-kv"><span>Total</span><span>{plan ? formatNaira(totalKobo(plan.priceKobo)) : "-"}</span></div>
          <p className="muted" style={{ margin: "14px 0" }}>The customer goes online once the phone attaches to the network. This sale appears in the line's History tab.</p>
          <div className="sell-actions">
            <Link className="btn btn--outline" to={`/lines/${r.imsi}`}>View line</Link>
            <button type="button" className="btn" onClick={reset}>Sell another SIM</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="sell">
      <h1>Sell SIM</h1>
      <Stepper current={step} onGo={setStep} />
      <div className="sell__grid">
        <div className="sell__main">
          {step === 0 && !customer && <CustomerStep onSelect={setCustomer} />}
          {step === 0 && customer && <CustomerCard customer={customer} onChange={() => setCustomer(null)} />}
          {step > 0 && customer && <CustomerCard customer={customer} />}
          {step === 1 && <SimNumberStep sim={sim} msisdn={msisdn} onSim={setSim} onMsisdn={setMsisdn} />}
          {step === 2 && <PlanStep plan={plan} onPlan={setPlan} />}
          {step === 3 && (
            <div className="card">
              <h3>Review</h3>
              <p className="muted">Check the details on the right, then activate the line. One activation request is sent for this sale.</p>
              {plan && <p style={{ marginTop: 8 }}>{plan.name} for {customer?.name}, number {msisdn}.</p>}
            </div>
          )}
        </div>

        <OrderSummary sim={sim} msisdn={msisdn} plan={plan}>
          {customer && step >= 2 && (!kycVerified || blocked) && (
            <div className="alert alert--danger" role="alert" style={{ margin: "14px 0" }}>
              <b>{blocked ? "This customer is blocked and cannot be sold a SIM." : KYC_MESSAGE}</b>
            </div>
          )}
          {activate.isError && <div className="alert alert--danger" role="alert" style={{ margin: "14px 0" }}>Activation failed: {activate.error.message}. You can try again; the sale will not be repeated.</div>}
          <div className="sell-actions" style={{ marginTop: 16 }}>
            {step > 0 && <button type="button" className="btn btn--outline" onClick={() => setStep(step - 1)} disabled={activate.isPending}>Back</button>}
            <button type="button" className="btn sell-actions__main" onClick={next} disabled={!canContinue || activate.isPending}>
              {activate.isPending ? "Activating..." : CONTINUE[step]}
            </button>
          </div>
        </OrderSummary>
      </div>

      <section className="card sell-next">
        <h3>After you activate</h3>
        <div className="sell-next__row">
          {[["Payment recorded", "Plan price and VAT are added to the ledger"], ["Line created on the network", "RatelBSS asks RatelLink to activate the SIM"], ["Customer goes online", "Data and calls work once the phone attaches"]].map(([t, s], i) => (
            <div key={t} className="sell-next__item"><span className="sell-next__n">{i + 1}</span><div><b>{t}</b><div className="muted">{s}</div></div></div>
          ))}
        </div>
      </section>
    </div>
  );
}