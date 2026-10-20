import { useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "../../components/ui";
import { formatGB, formatNaira } from "../../lib/format";
import { getBundles, getPlans } from "./api";
import { bundleToForm, emptyForm, planToForm } from "./form";
import { OfferDrawer } from "./OfferDrawer";
import type { Kind, OfferStatus } from "./types";
import "./PlansScreen.css";

const StatusBadge = ({ status }: { status: OfferStatus }) => (status === "on_sale" ? <Badge tone="green">On sale</Badge> : <Badge tone="grey">Retired</Badge>);

// ?open=plan:p2 | bundle:b1 | new:plan | new:bundle  (the open drawer lives in the URL)
function parseOpen(v: string | null): { kind: Kind; id: string | null } | null {
  const [a, b] = (v ?? "").split(":");
  if (a === "new" && (b === "plan" || b === "bundle")) return { kind: b, id: null };
  if ((a === "plan" || a === "bundle") && b) return { kind: a, id: b };
  return null;
}

export default function PlansScreen() {
  const [params, setParams] = useSearchParams();
  const open = parseOpen(params.get("open"));
  const plans = useQuery({ queryKey: ["plans"], queryFn: getPlans });
  const bundles = useQuery({ queryKey: ["bundles"], queryFn: getBundles });
  const setOpen = (v: string | null) => setParams(v ? { open: v } : {}, { replace: true });

  // Work out what the drawer should show.
  let drawer: { kind: Kind; id: string | null; status: OfferStatus; initial: ReturnType<typeof emptyForm> } | null = null;
  if (open?.id === null) drawer = { kind: open.kind, id: null, status: "on_sale", initial: emptyForm() };
  else if (open?.kind === "plan") {
    const p = plans.data?.find((x) => x.planId === open.id);
    if (p) drawer = { kind: "plan", id: p.planId, status: p.status, initial: planToForm(p) };
  } else if (open?.kind === "bundle") {
    const b = bundles.data?.find((x) => x.bundleId === open.id);
    if (b) drawer = { kind: "bundle", id: b.bundleId, status: b.status, initial: bundleToForm(b) };
  }

  return (
    <div className={`plans${drawer ? " plans--open" : ""}`}>
      <div className="plans__title">
        <div>
          <h1>Plans &amp; Bundles</h1>
          <p className="muted">What Ratelplus sells today.</p>
        </div>
        <div className="plans__buttons">
          <button type="button" className="btn btn--outline" onClick={() => setOpen("new:bundle")}>Create bundle</button>
          <button type="button" className="btn" onClick={() => setOpen("new:plan")}>Create plan</button>
        </div>
      </div>

      <section className="card plans__card">
        <h3>Plans</h3>
        {plans.isError ? <div className="plans__message">Could not load plans. <button type="button" className="btn btn--sm" onClick={() => plans.refetch()}>Try again</button></div> : (
          <table className="data-table">
            <thead><tr><th>Plan</th><th>Price</th><th>Validity</th><th>Data</th><th>Speed up/down</th><th>When data runs out</th><th>Status</th></tr></thead>
            <tbody>
              {plans.isPending && <tr><td colSpan={7} className="muted">Loading...</td></tr>}
              {plans.data?.map((p) => (
                <tr key={p.planId} className={open?.id === p.planId ? "plans-row--on" : ""} onClick={() => setOpen(`plan:${p.planId}`)}>
                  <td><button type="button" className="plans-name" onClick={(e) => { e.stopPropagation(); setOpen(`plan:${p.planId}`); }}>{p.name}</button></td>
                  <td>{formatNaira(p.priceKobo)}</td><td>{p.validityDays} days</td><td>{formatGB(p.dataBytes)}</td>
                  <td>{p.speedUlMbps}/{p.speedDlMbps} Mbps</td><td>{p.onExhaustion === "slow" ? "Slow down" : "Stop internet"}</td>
                  <td><StatusBadge status={p.status} /></td>
                </tr>
              ))}
              {plans.data?.length === 0 && <tr><td colSpan={7} className="muted">No plans yet. Use "Create plan".</td></tr>}
            </tbody>
          </table>
        )}
      </section>

      <section className="card plans__card">
        <h3>Bundles <span className="muted plans__hint">extra data on top of a plan</span></h3>
        {bundles.isError ? <div className="plans__message">Could not load bundles. <button type="button" className="btn btn--sm" onClick={() => bundles.refetch()}>Try again</button></div> : (
          <table className="data-table">
            <thead><tr><th>Bundle</th><th>Price</th><th>Validity</th><th>Data</th><th>Status</th></tr></thead>
            <tbody>
              {bundles.isPending && <tr><td colSpan={5} className="muted">Loading...</td></tr>}
              {bundles.data?.map((b) => (
                <tr key={b.bundleId} className={open?.id === b.bundleId ? "plans-row--on" : ""} onClick={() => setOpen(`bundle:${b.bundleId}`)}>
                  <td><button type="button" className="plans-name" onClick={(e) => { e.stopPropagation(); setOpen(`bundle:${b.bundleId}`); }}>{b.name}</button></td>
                  <td>{formatNaira(b.priceKobo)}</td><td>{b.validityDays} days</td><td>{formatGB(b.dataBytes)}</td><td><StatusBadge status={b.status} /></td>
                </tr>
              ))}
              {bundles.data?.length === 0 && <tr><td colSpan={5} className="muted">No bundles yet. Use "Create bundle".</td></tr>}
            </tbody>
          </table>
        )}
      </section>

      {drawer && <OfferDrawer key={params.get("open")} kind={drawer.kind} id={drawer.id} status={drawer.status} initial={drawer.initial} onClose={() => setOpen(null)} />}
    </div>
  );
}
