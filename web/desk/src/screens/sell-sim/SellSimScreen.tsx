import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { keyFor, type KeySlot } from "../../lib/api";
import { createLine } from "./api";
import { CollectPayment } from "./CollectPayment";
import { CustomerCard, CustomerStep } from "./CustomerStep";
import { OrderSummary } from "./OrderSummary";
import { PlanStep } from "./PlanStep";
import { SimNumberStep } from "./SimNumberStep";
import { Stepper } from "./Stepper";
import type { Customer, FreeSim, Plan } from "./types";
import "./SellSimScreen.css";

const CONTINUE = ["Continue", "Continue", "Continue to review", "Create line"];
const KYC_MESSAGE = "A line cannot be activated until KYC is verified.";

export default function SellSimScreen() {
  const queryClient = useQueryClient();
  const [step, setStep] = useState(0);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [sim, setSim] = useState<FreeSim | null>(null);
  const [msisdn, setMsisdn] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const slot = useRef<KeySlot>({ signature: null, key: null }); // one key per distinct sale; a retry of the same sale reuses it

  const create = useMutation({
    mutationFn: () => {
      const req = { customerId: customer!.id, iccid: sim!.iccid, msisdn, planId: plan!.planId };
      return createLine(req, keyFor(slot.current, JSON.stringify(req)));
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["lines"] });
      void queryClient.invalidateQueries({ queryKey: ["stock"] });
    },
  });

  const kycVerified = customer?.kycStatus === "verified";
  const blocked = customer?.blocked ?? false;
  // KYC hard gate: from the plan step onward the button stays disabled until the customer is verified.
  const canContinue = [!!customer && !blocked, !!sim && !!msisdn, !!plan && kycVerified && !blocked, !!plan && kycVerified && !blocked][step];

  const reset = () => {
    setStep(0); setCustomer(null); setSim(null); setMsisdn(""); setPlan(null);
    create.reset();
  };
  const next = () => (step < 3 ? setStep(step + 1) : create.mutate());

  if (create.isSuccess) return <CollectPayment line={create.data} customerName={customer!.name} plan={plan!} onAnother={reset} />;

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
              <p className="muted">Check the details on the right, then create the line. Next you collect the payment and activate it.</p>
              {plan && <p style={{ marginTop: 8 }}>{plan.name} for {customer?.name}.</p>}
            </div>
          )}
        </div>

        <OrderSummary sim={sim} msisdn={msisdn} plan={plan}>
          {customer && step >= 2 && (!kycVerified || blocked) && (
            <div className="alert alert--danger" role="alert" style={{ margin: "14px 0" }}>
              <b>{blocked ? "This customer is blocked and cannot be sold a SIM." : KYC_MESSAGE}</b>
            </div>
          )}
          {create.isError && <div className="alert alert--danger" role="alert" style={{ margin: "14px 0" }}>The line was not created: {create.error.message}. You can try again; the sale will not be repeated.</div>}
          <div className="sell-actions" style={{ marginTop: 16 }}>
            {step > 0 && <button type="button" className="btn btn--outline" onClick={() => setStep(step - 1)} disabled={create.isPending}>Back</button>}
            <button type="button" className="btn sell-actions__main" onClick={next} disabled={!canContinue || create.isPending}>
              {create.isPending ? "Creating..." : CONTINUE[step]}
            </button>
          </div>
        </OrderSummary>
      </div>

      <section className="card sell-next">
        <h3>After you create the line</h3>
        <div className="sell-next__row">
          {[["Customer pays", "They top up the line's wallet on RatelPay with a prepaid card"], ["You buy the plan", "The plan's price is taken from the wallet, VAT included"], ["You activate", "RatelBSS asks RatelLink to switch the SIM on; data and calls work once the phone attaches"]].map(([t, s], i) => (
            <div key={t} className="sell-next__item"><span className="sell-next__n">{i + 1}</span><div><b>{t}</b><div className="muted">{s}</div></div></div>
          ))}
        </div>
      </section>
    </div>
  );
}
