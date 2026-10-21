import type { ReactNode } from "react";
import { formatNaira } from "../../lib/format";
import { totalKobo, vatKobo } from "./pricing";
import type { FreeSim, Plan } from "./types";

interface Props { sim: FreeSim | null; msisdn: string; plan: Plan | null; children: ReactNode }

export function OrderSummary({ sim, msisdn, plan, children }: Props) {
  const vat = plan ? vatKobo(plan.priceKobo) : 0;
  const rows: [string, string][] = [
    ["SIM (ICCID)", sim?.iccid ?? "Not chosen yet"],
    ["Number", msisdn || "Not chosen yet"],
    [plan?.name ?? "Plan", plan ? formatNaira(plan.priceKobo) : "Not chosen yet"],
    ["VAT (7.5%)", plan ? formatNaira(vat) : "-"],
  ];
  return (
    <aside className="card sell-summary" aria-label="Order summary">
      <h3>Order summary</h3>
      {rows.map(([k, v]) => <div className="sell-kv" key={k}><span>{k}</span><span>{v}</span></div>)}
      <div className="sell-kv sell-kv--total"><b>Total</b><b>{plan ? formatNaira(totalKobo(plan.priceKobo)) : "-"}</b></div>
      {children}
    </aside>
  );
}