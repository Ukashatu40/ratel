import { useState } from "react";
import { useSearchParams } from "react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AreaChart, BarChart, DonutChart } from "../../components/charts/charts";
import { formatBytesAuto, formatCount, formatDateShort, formatLongDate, formatClock, formatNaira, formatNairaCompact, weekdayShort } from "../../lib/format";
import { getOverview } from "./api";
import { ReconciliationCard } from "./ReconciliationCard";
import { StatCard } from "./StatCard";
import "./ReportsScreen.css";

const RANGES = [7, 14, 30] as const;
const COLORS = ["#00338d", "#4f7bd0", "#ffcc00", "#e4002b", "#94a3b8"];

// "▲ 7.9% on yesterday". No percentage when there is nothing to compare with.
function change(last: number, prev: number) {
  if (!prev) return "No change to compare";
  const p = ((last - prev) / prev) * 100;
  return `${p >= 0 ? "▲" : "▼"} ${Math.abs(p).toFixed(1)}% on yesterday`;
}

export default function ReportsScreen() {
  const [params, setParams] = useSearchParams();
  const asked = Number(params.get("days"));
  const days = (RANGES as readonly number[]).includes(asked) ? asked : 14; // the range lives in the URL
  const [now] = useState(() => new Date());
  const { data, isPending, isError, refetch } = useQuery({ queryKey: ["reports", "overview", days], queryFn: () => getOverview(days), placeholderData: keepPreviousData, refetchInterval: 60_000 });

  // With many days, label only some of the bars so they stay readable. The last day is always labelled.
  const step = days <= 7 ? 1 : days <= 14 ? 2 : 5;
  const label = (i: number, date: string) => ((days - 1 - i) % step === 0 ? (days <= 7 ? weekdayShort(date) : formatDateShort(date)) : "");

  const content = () => {
    if (isError) return <div className="card rep-message">Could not load the reports. <button type="button" className="btn btn--sm" onClick={() => refetch()}>Try again</button></div>;
    if (isPending) return <div className="rep-stats">{[0, 1, 2].map((i) => <div key={i} className="card skeleton" style={{ height: 120 }} aria-busy="true" />)}</div>;
    const s = data.salesPerDay, u = data.dataUsagePerDay, v = data.voucherRedemptionsPerDay, n = s.length;
    const net = data.revenueByPlan.reduce((t, p) => t + p.revenueKobo, 0) || 1;
    return (
      <>
        <div className="rep-stats">
          <StatCard label="Daily sales revenue" value={formatNaira(s[n - 1].revenueKobo)} delta={change(s[n - 1].revenueKobo, s[n - 2]?.revenueKobo ?? 0)} note={`includes ${formatNaira(s[n - 1].vatKobo)} VAT`} spark={s.slice(-7).map((x) => x.revenueKobo)} />
          <StatCard label="Data usage total" value={formatBytesAuto(u[n - 1].bytes)} delta={change(u[n - 1].bytes, u[n - 2]?.bytes ?? 0)} spark={u.slice(-7).map((x) => x.bytes)} />
          <StatCard label="Voucher redemptions" value={formatCount(v[n - 1].count)} delta={change(v[n - 1].count, v[n - 2]?.count ?? 0)} note={`worth ${formatNaira(v[n - 1].valueKobo)}`} spark={v.slice(-7).map((x) => x.count)} />
        </div>

        <div className="rep-row rep-row--wide">
          <section className="card">
            <h3>Sales revenue, last {days} days (₦ thousands)</h3>
            <AreaChart values={s.map((x) => Math.round(x.revenueKobo / 100 / 1000))} labels={s.map((x, i) => label(i, x.date))} formatTick={(k) => `${Math.round(k)}k`} height={230} />
          </section>
          <section className="card">
            <h3>Revenue by plan <span className="muted rep-hint">before VAT</span></h3>
            <div className="rep-donut">
              <DonutChart parts={data.revenueByPlan.map((p, i) => ({ value: p.revenueKobo, color: COLORS[i % COLORS.length] }))} centerValue={formatNairaCompact(net)} centerLabel={`${days} days`} size={180} thickness={24} />
              <ul className="rep-legend">
                {data.revenueByPlan.map((p, i) => (
                  <li key={p.name}><span><i style={{ background: COLORS[i % COLORS.length] }} />{p.name}</span><b>{Math.round((p.revenueKobo / net) * 100)}%</b></li>
                ))}
              </ul>
            </div>
          </section>
        </div>

        <div className="rep-row">
          <section className="card"><h3>Data usage per day (TB)</h3><BarChart values={u.map((x) => Math.round(x.bytes / 1e11) / 10)} labels={u.map((x, i) => label(i, x.date))} width={520} height={190} /></section>
          <section className="card"><h3>Voucher redemptions per day</h3><BarChart values={v.map((x) => x.count)} labels={v.map((x, i) => label(i, x.date))} width={520} height={190} /></section>
          <ReconciliationCard />
        </div>
      </>
    );
  };

  return (
    <div className="rep">
      <div className="rep-title">
        <div>
          <h1>Reports</h1>
          <p className="muted">{formatLongDate(now)}, up to {formatClock(now)} WAT.</p>
        </div>
        <div className="rep-ranges" role="group" aria-label="Date range">
          {RANGES.map((r) => (
            <button key={r} type="button" className={`chip${days === r ? " chip--on" : ""}`} aria-pressed={days === r} onClick={() => setParams(r === 14 ? {} : { days: String(r) }, { replace: true })}>{r} days</button>
          ))}
        </div>
      </div>
      {content()}
    </div>
  );
}
