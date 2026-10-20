import { useQuery } from "@tanstack/react-query";
import { getAvailableNumbers, getFreeSims } from "./api";
import type { FreeSim } from "./types";

interface Props { sim: FreeSim | null; msisdn: string; onSim: (s: FreeSim | null) => void; onMsisdn: (n: string) => void }

export function SimNumberStep({ sim, msisdn, onSim, onMsisdn }: Props) {
  const sims = useQuery({ queryKey: ["stock", "sims", "in_stock"], queryFn: getFreeSims });
  const numbers = useQuery({ queryKey: ["stock", "numbers", "available"], queryFn: getAvailableNumbers });
  return (
    <div className="card">
      <h3>SIM and number</h3>
      {(sims.isError || numbers.isError) && <div className="alert alert--danger" style={{ marginBottom: 12 }}>Could not load stock. <button type="button" className="btn btn--sm" onClick={() => { void sims.refetch(); void numbers.refetch(); }}>Try again</button></div>}
      <div className="sell-form">
        <div className="field">
          <label htmlFor="sim-select">Free SIM in stock (ICCID)</label>
          <select id="sim-select" className="input" value={sim?.iccid ?? ""} onChange={(e) => onSim(sims.data?.find((s) => s.iccid === e.target.value) ?? null)} disabled={sims.isPending}>
            <option value="">{sims.isPending ? "Loading..." : "Choose a SIM"}</option>
            {sims.data?.map((s) => <option key={s.iccid} value={s.iccid}>{s.iccid}  (batch {s.batch})</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="number-select">Available number</label>
          <select id="number-select" className="input" value={msisdn} onChange={(e) => onMsisdn(e.target.value)} disabled={numbers.isPending}>
            <option value="">{numbers.isPending ? "Loading..." : "Choose a number"}</option>
            {numbers.data?.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
      </div>
    </div>
  );
}