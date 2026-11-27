import { useSearchParams } from "react-router";
import { stockTabOffered } from "../../lib/features";
import { NumbersTab } from "./NumbersTab";
import { SimsTab } from "./SimsTab";
import { StockHistoryTab } from "./StockHistoryTab";
import { VouchersTab } from "./VouchersTab";
import "./StockScreen.css";

const TABS = [{ key: "sims", label: "SIMs" }, { key: "numbers", label: "Numbers" }, { key: "vouchers", label: "Vouchers" }, { key: "history", label: "History" }] as const;
type TabKey = (typeof TABS)[number]["key"];

export default function StockScreen() {
  const [params, setParams] = useSearchParams();
  // Against the real API only the tabs it serves are shown (lib/features.ts); on mock data, all of them.
  const tabs = TABS.filter((t) => stockTabOffered(t.key));
  const first = tabs[0].key;
  const asked = params.get("tab");
  const tab: TabKey = tabs.find((t) => t.key === asked)?.key ?? first; // the open tab lives in the URL
  return (
    <div className="stock">
      <div>
        <h1>Stock &amp; Vouchers</h1>
        <p className="muted" style={{ marginTop: 4 }}>{tabs.length > 1 ? "SIMs, numbers and top-up cards." : "Top-up cards: request, approve, print, stock and sell."}</p>
      </div>
      <div className="stock-tabs" role="tablist">
        {tabs.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} className={tab === t.key ? "on" : ""} onClick={() => setParams(t.key === first ? {} : { tab: t.key }, { replace: true })}>{t.label}</button>
        ))}
      </div>
      {tab === "sims" && <SimsTab />}
      {tab === "numbers" && <NumbersTab />}
      {tab === "vouchers" && <VouchersTab />}
      {tab === "history" && <StockHistoryTab />}
    </div>
  );
}
