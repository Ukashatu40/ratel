import { useQuery } from "@tanstack/react-query";
import { CollectPayment } from "../sell-sim/CollectPayment";
import { getPlan } from "../sell-sim/api";
import type { LineDetail } from "./types";

// A line that is still awaiting activation: pick the sale up where it stopped (the customer's top-up, the purchase, the
// activation). The line, its wallet and its purchase live on the server, so this works after a closed window too.
export function ContinueSale({ line }: { line: LineDetail }) {
  const plan = useQuery({ queryKey: ["plan", line.planId], queryFn: () => getPlan(line.planId) });
  if (plan.isPending) return <div className="card skeleton" style={{ height: 120 }} aria-busy="true" />;
  if (plan.isError || !plan.data) return <div className="alert alert--danger">The plan of this line could not be loaded, so the sale cannot be continued here. Try again later.</div>;
  return (
    <CollectPayment
      line={{ lineId: line.lineId, imsi: line.imsi, msisdn: line.msisdn, planId: line.planId, state: line.state, expiresAt: line.planEndsEpoch }}
      customerName={line.customerName}
      plan={plan.data}
    />
  );
}
