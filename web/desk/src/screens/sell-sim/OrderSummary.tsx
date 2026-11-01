import type { ReactNode } from "react";
import { formatMsisdn, formatNaira } from "../../lib/format";
import type { FreeSim, Plan } from "./types";

interface Props { sim: FreeSim | null; msisdn: string; plan: Plan | null; children: ReactNode }

// The plan's price is what the wallet is debited and already includes the VAT (the API splits it when the plan is bought).
export function OrderSummary({ sim, msisdn, plan, children }: Props) {
  const rows: [string, string][] = [
    ["SIM (ICCID)", sim?.iccid ?? "Not chosen yet"],
    ["Number", msisdn ? formatMsisdn(msisdn) : "Not chosen yet"],
    [plan?.name ?? "Plan", plan ? formatNaira(plan.priceKobo) : "Not chosen yet"],
  ];
  return (
    <aside className="card sell-summary" aria-label="Order summary">
      <h3>Order summary</h3>
      {rows.map(([k, v]) => <div className="sell-kv" key={k}><span>{k}</span><span>{v}</span></div>)}
      <div className="sell-kv sell-kv--total"><b>Total (VAT included)</b><b>{plan ? formatNaira(plan.priceKobo) : "-"}</b></div>
      {children}
    </aside>
  );
}
