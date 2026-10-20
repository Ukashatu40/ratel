import { useSearchParams } from "react-router";
import { NumbersTab } from "./NumbersTab";
import { SimsTab } from "./SimsTab";
import { StockHistoryTab } from "./StockHistoryTab";
import { VouchersTab } from "./VouchersTab";
import "./StockScreen.css";

const TABS = [{ key: "sims", label: "SIMs" }, { key: "numbers", label: "Numbers" }, { key: "vouchers", label: "Vouchers" }, { key: "history", label: "History" }] as const;
type TabKey = (typeof TABS)[number]["key"];
const isTab = (v: string | null): v is TabKey => TABS.some((t) => t.key === v);

export default function StockScreen() {
  const [params, setParams] = useSearchParams();
  const tab: TabKey = isTab(params.get("tab")) ? (params.get("tab") as TabKey) : "sims"; // the open tab lives in the URL
  return (
    <div className="stock">
      <div>
        <h1>Stock &amp; Vouchers</h1>
        <p className="muted" style={{ marginTop: 4 }}>SIMs, numbers and top-up cards.</p>
      </div>
      <div className="stock-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} className={tab === t.key ? "on" : ""} onClick={() => setParams(t.key === "sims" ? {} : { tab: t.key }, { replace: true })}>{t.label}</button>
        ))}
      </div>
      {tab === "sims" && <SimsTab />}
      {tab === "numbers" && <NumbersTab />}
      {tab === "vouchers" && <VouchersTab />}
      {tab === "history" && <StockHistoryTab />}
    </div>
  );
}
