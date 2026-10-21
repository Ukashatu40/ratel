import { useQuery } from "@tanstack/react-query";
import { Badge } from "../../components/ui";
import { formatGB, formatNaira } from "../../lib/format";
import { getPlansOnSale } from "./api";
import type { Plan } from "./types";

const exhaustion = (p: Plan) => (p.onExhaustion === "slow" ? `slow down (${p.slowUlMbps} / ${p.slowDlMbps} Mbps)` : "stop internet");

export function PlanStep({ plan, onPlan }: { plan: Plan | null; onPlan: (p: Plan) => void }) {
  const { data, isPending, isError, refetch } = useQuery({ queryKey: ["plans", "on_sale"], queryFn: getPlansOnSale });
  if (isPending) return <div className="sell-plans">{[0, 1, 2].map((i) => <div key={i} className="card skeleton" />)}</div>;
  if (isError) return <div className="alert alert--danger">Could not load plans. <button type="button" className="btn btn--sm" onClick={() => refetch()}>Try again</button></div>;
  return (
    <div className="sell-plans" role="radiogroup" aria-label="Plans on sale">
      {data.map((p) => {
        const selected = plan?.planId === p.planId;
        return (
          <button type="button" role="radio" aria-checked={selected} key={p.planId} className={`sell-plan${selected ? " sell-plan--on" : ""}`} onClick={() => onPlan(p)}>
            <div className="sell-plan__title"><b>{p.name}</b>{selected && <Badge tone="blue">Selected</Badge>}</div>
            <div className="sell-plan__price">{formatNaira(p.priceKobo)}</div>
            <div className="muted">{p.validityDays} days &nbsp;|&nbsp; {formatGB(p.dataBytes)} &nbsp;|&nbsp; {p.speedUlMbps} up / {p.speedDlMbps} down Mbps</div>
            <div style={{ marginTop: 8 }}>When data runs out: {exhaustion(p)}</div>
          </button>
        );
      })}
    </div>
  );
}