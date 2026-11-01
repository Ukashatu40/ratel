import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { Badge } from "../../components/ui";
import { AreaChart, DonutChart } from "../../components/charts/charts";
import { formatCount, formatLongDate, formatNaira, greeting, weekdayShort } from "../../lib/format";
import { useCurrentUser } from "../../lib/useCurrentUser";
import { getDashboard } from "./api";
import { KpiCard } from "./KpiCard";
import { AttentionTable } from "./AttentionTable";
import type { DashboardData, LineState } from "./types";
import "./DashboardScreen.css";

const STATES: { state: LineState; label: string; color: string }[] = [
  { state: "active", label: "Active", color: "#008751" },
  { state: "out_of_data", label: "Out of data", color: "#e4002b" },
  { state: "awaiting_activation", label: "Awaiting activation", color: "#4f7bd0" },
  { state: "suspended", label: "Suspended", color: "#ffcc00" },
  { state: "expired", label: "Expired", color: "#94a3b8" },
  { state: "terminated", label: "Terminated", color: "#475569" },
];

const arrow = (n: number) => (n >= 0 ? "▲" : "▼");
const last = (a: number[]) => a[a.length - 1];
const prev = (a: number[]) => a[a.length - 2];

function Kpis({ d }: { d: DashboardData }) {
  // The line KPIs show a trend only when the API gives one; the real API does not (no daily snapshots of line counts).
  const t = d.trends;
  const weekChange = t ? last(t.active) - t.active[0] : 0;
  const outChange = t ? last(t.outOfData) - prev(t.outOfData) : 0;
  const kycChange = t ? last(t.kycPending) - prev(t.kycPending) : 0;
  const topupDelta =
    d.topupsYesterdayKobo === 0
      ? (d.topupsTodayKobo === 0 ? "No top-ups yet" : "No top-ups yesterday")
      : (() => { const c = ((d.topupsTodayKobo - d.topupsYesterdayKobo) / d.topupsYesterdayKobo) * 100; return `${arrow(c)} ${Math.abs(c).toFixed(1)}% on yesterday`; })();
  return (
    <div className="dash__kpis">
      <KpiCard label="Active Lines" value={formatCount(d.counts.active)} badge={<Badge tone="green">Active</Badge>} delta={t ? `${arrow(weekChange)} ${Math.abs(weekChange)} this week` : undefined} spark={t?.active} icon="lines" tone="green" />
      <KpiCard label="Out of Data Lines" value={formatCount(d.counts.out_of_data)} badge={<Badge tone="red">Out of data</Badge>} delta={t ? `${arrow(outChange)} ${Math.abs(outChange)} since yesterday` : undefined} spark={t?.outOfData} icon="stock" tone="red" />
      <KpiCard label="Waiting for KYC" value={formatCount(d.kycPending)} badge={<Badge tone="amber">Pending KYC</Badge>} delta={t ? `${arrow(kycChange)} ${Math.abs(kycChange)} since yesterday` : undefined} spark={t?.kycPending} icon="customers" tone="amber" />
      <KpiCard label="Top-ups Today" value={formatNaira(d.topupsTodayKobo)} badge={<Badge tone="amber">Since 00:00 WAT</Badge>} delta={topupDelta} spark={d.topupsLast7Days.map((p) => p.amountKobo)} icon="wallet" tone="navy" />
    </div>
  );
}

function LoadingState() {
  return (
    <div className="dash__kpis" aria-busy="true" aria-label="Loading dashboard">
      {[0, 1, 2, 3].map((i) => <div key={i} className="card skeleton" />)}
    </div>
  );
}

export default function DashboardScreen() {
  const user = useCurrentUser();
  const { data, isPending, isError, refetch } = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard, refetchInterval: 60_000 });
  const [now] = useState(() => new Date()); // fixed for this visit; the header clock keeps ticking
  const total = data ? STATES.reduce((s, x) => s + data.counts[x.state], 0) : 0;

  return (
    <div className="dash">
      <div className="dash__title">
        <div>
          <h1>{greeting(now)}, {user.name.split(" ")[0]}</h1>
          <p className="muted">{formatLongDate(now)}. Here is what needs your attention.</p>
        </div>
        <Link to="/sales/activate" className="btn">Sell SIM</Link>
      </div>

      {isPending && <LoadingState />}
      {isError && (
        <div className="card dash__error">
          <b>The dashboard could not be loaded.</b>
          <button className="btn btn--sm" onClick={() => refetch()}>Try again</button>
        </div>
      )}

      {data && (
        <>
          <Kpis d={data} />
          <div className="dash__charts">
            <section className="card">
              <div className="dash__cardhead">
                <h3>Top-ups this week (₦ thousands)</h3>
                <button className="chip chip--on">7 days</button>
                <button className="chip" disabled title="Needs a 30-day series from the API">30 days</button>
              </div>
              <AreaChart values={data.topupsLast7Days.map((p) => p.amountKobo)} labels={data.topupsLast7Days.map((p) => weekdayShort(p.date))} formatTick={(kobo) => `${Math.round(kobo / 100 / 1000)}k`} height={195} />
            </section>
            <section className="card">
              <h3>Lines by state</h3>
              <div className="dash__donut">
                <DonutChart parts={STATES.map((s) => ({ value: data.counts[s.state], color: s.color }))} centerValue={formatCount(total)} centerLabel="lines" />
                <ul className="dash__legend">
                  {STATES.map((s) => (
                    <li key={s.state}><span><i style={{ background: s.color }} />{s.label}</span><b>{formatCount(data.counts[s.state])}</b></li>
                  ))}
                </ul>
              </div>
            </section>
          </div>
          <AttentionTable items={data.attention} />
        </>
      )}
    </div>
  );
}