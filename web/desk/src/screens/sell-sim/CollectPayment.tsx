import { useState } from "react";
import { Link } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { newIdempotencyKey } from "../../lib/api";
import { formatMsisdn, formatNaira, formatWAT } from "../../lib/format";
import { activateLine, buyPlan, getWallet, isMock } from "./api";
import { mockTopUp } from "./mock";
import type { CreatedLine, Plan, Purchase } from "./types";

// Where the customer tops up. RatelPay is served by the same proxy as the API, at /pay; set VITE_PAY_PAGE_URL if it is not.
const PAY_URL: string = import.meta.env.VITE_PAY_PAGE_URL ?? `${window.location.origin}/pay`;

interface Props { line: CreatedLine; customerName: string; plan: Plan; onAnother?: () => void }

// After the line exists: the customer tops up its wallet on the RatelPay page with a prepaid card, staff buy the plan
// from that wallet, then activate. Each step is one call with its own Idempotency-Key, so a retry cannot repeat it.
// The line, its wallet and its purchase live on the server: leaving this page loses nothing.
export function CollectPayment({ line, customerName, plan, onAnother }: Props) {
  const queryClient = useQueryClient();
  const [purchase, setPurchase] = useState<Purchase | null>(null);
  const [buyKey] = useState(newIdempotencyKey);
  const [activateKey] = useState(newIdempotencyKey);

  const wallet = useQuery({ queryKey: ["wallet", line.lineId], queryFn: () => getWallet(line.lineId), refetchInterval: purchase ? false : 5000 });
  const buy = useMutation({
    mutationFn: () => buyPlan(line.lineId, plan.planId, buyKey),
    onSuccess: (p) => { setPurchase(p); void queryClient.invalidateQueries({ queryKey: ["wallet", line.lineId] }); },
  });
  const activate = useMutation({
    mutationFn: () => activateLine(line.lineId, activateKey),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["lines"] });
      void queryClient.invalidateQueries({ queryKey: ["line", String(line.lineId)] });
    },
  });

  if (activate.isSuccess) {
    const ends = activate.data.expiresAt ?? purchase?.validTo ?? null;
    return (
      <div className="sell">
        <h1>Line activated</h1>
        <div className="card sell-done">
          <h3>{formatMsisdn(line.msisdn)} is ready</h3>
          <div className="sell-kv"><span>Customer</span><span>{customerName}</span></div>
          <div className="sell-kv"><span>Plan</span><span>{plan.name}</span></div>
          {ends !== null && <div className="sell-kv"><span>Plan ends</span><span>{formatWAT(ends)}</span></div>}
          <div className="sell-kv"><span>Paid from the wallet</span><span>{formatNaira(purchase?.priceKobo ?? plan.priceKobo)}</span></div>
          {purchase && purchase.vatKobo > 0 && <div className="sell-kv"><span>of which VAT</span><span>{formatNaira(purchase.vatKobo)}</span></div>}
          <p className="muted" style={{ margin: "14px 0" }}>The customer goes online once the phone attaches to the network. This sale appears in the line's History tab.</p>
          <div className="sell-actions">
            <Link className="btn btn--outline" to={`/lines/${line.lineId}`}>View line</Link>
            {onAnother && <button type="button" className="btn" onClick={onAnother}>Sell another SIM</button>}
          </div>
        </div>
      </div>
    );
  }

  const balance = wallet.data?.balanceKobo ?? null;
  const shortfall = balance === null ? null : Math.max(0, plan.priceKobo - balance);
  const covered = shortfall === 0;

  return (
    <div className="sell">
      <h1>Collect payment and activate</h1>
      <div className="card" style={{ marginBottom: 16 }}>
        <h3>Line for {customerName}</h3>
        <p className="muted">{formatMsisdn(line.msisdn)} is waiting for activation. Nothing is charged until you buy the plan. The line, its wallet and its purchase are kept: you can leave this page and come back from the line.</p>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3>1. The customer tops up</h3>
        <p>Ask the customer to open <b>{PAY_URL}</b> and top up the number <b>{formatMsisdn(line.msisdn)}</b> with a prepaid card.</p>
        <div className="sell-kv"><span>{plan.name} costs (VAT included)</span><span>{formatNaira(plan.priceKobo)}</span></div>
        <div className="sell-kv"><span>Wallet balance</span><span>{balance === null ? (wallet.isError ? "Could not load" : "Loading...") : formatNaira(balance)}</span></div>
        {shortfall !== null && shortfall > 0 && !purchase && <div className="sell-kv"><span>Still to pay</span><b>{formatNaira(shortfall)}</b></div>}
        <div className="sell-actions" style={{ marginTop: 12 }}>
          <button type="button" className="btn btn--outline" onClick={() => void wallet.refetch()} disabled={wallet.isFetching}>{wallet.isFetching ? "Checking..." : "Refresh balance"}</button>
          {isMock() && !purchase && (
            <button type="button" className="btn btn--outline" onClick={() => { mockTopUp(line.lineId, plan.priceKobo); void wallet.refetch(); }}>Simulate a card top-up (mock only)</button>
          )}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3>2. Buy the plan</h3>
        {purchase ? (
          <p>Bought for {formatNaira(purchase.priceKobo)}{purchase.vatKobo > 0 ? `, of which ${formatNaira(purchase.vatKobo)} is VAT` : ""}. Wallet balance now {formatNaira(purchase.balanceKobo)}.</p>
        ) : (
          <p className="muted">The wallet is debited the plan's price, once.</p>
        )}
        {buy.isError && <div className="alert alert--danger" role="alert" style={{ margin: "12px 0" }}>The plan was not bought: {buy.error.message}. You can try again; it will not be charged twice.</div>}
        <button type="button" className="btn" onClick={() => buy.mutate()} disabled={!covered || !!purchase || buy.isPending}>
          {buy.isPending ? "Buying..." : purchase ? "Plan bought" : "Buy plan"}
        </button>
      </div>

      <div className="card">
        <h3>3. Activate</h3>
        <p className="muted">RatelBSS asks the network to switch the SIM on, with the plan's speeds.</p>
        {activate.isError && <div className="alert alert--danger" role="alert" style={{ margin: "12px 0" }}>Activation was refused: {activate.error.message}. You can try again; the line is not activated twice.</div>}
        <button type="button" className="btn" onClick={() => activate.mutate()} disabled={!purchase || activate.isPending}>
          {activate.isPending ? "Activating..." : "Activate line"}
        </button>
      </div>
    </div>
  );
}
