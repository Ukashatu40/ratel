import { Link, useSearchParams } from "react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Badge, type Tone } from "../../components/ui";
import { GroupedBarChart, Sparkline } from "../../components/charts/charts";
import { formatCount, formatNaira, formatWAT, weekdayShort } from "../../lib/format";
import { getLedger, getWalletSummary } from "./api";
import { LineFinder } from "./LineFinder";
import { LineWalletCard } from "./LineWalletCard";
import type { EntryKind, LedgerTab } from "./types";
import "./WalletScreen.css";

const PAGE_SIZE = 10;
const TABS: { key: LedgerTab; label: string }[] = [
  { key: "all", label: "All" }, { key: "top_up", label: "Top-ups" }, { key: "plan_purchase", label: "Plan purchases" },
  { key: "vat", label: "VAT" }, { key: "voucher_redemption", label: "Vouchers" }, { key: "correction", label: "Corrections" },
];
const isTab = (v: string | null): v is LedgerTab => TABS.some((t) => t.key === v);
const KIND_TONE: Record<EntryKind, Tone> = { top_up: "green", plan_purchase: "blue", vat: "grey", voucher_redemption: "blue", correction: "amber" };

// +350,000 (₦3,500.00): the kobo value is what is stored, the naira value is for reading.
function Amount({ kobo }: { kobo: number }) {
  return (
    <span>
      <b className={kobo >= 0 ? "wal-in" : "wal-out"}>{kobo >= 0 ? "+" : "-"}{formatCount(Math.abs(kobo))}</b>{" "}
      <span className="muted">({formatNaira(Math.abs(kobo))})</span>
    </span>
  );
}

function SummaryCard({ label, value, delta, spark, navy }: { label: string; value: string; delta: string; spark: number[]; navy?: boolean }) {
  return (
    <div className={`card wal-card${navy ? " wal-card--navy" : ""}`}>
      <div className="wal-card__label">{label}</div>
      <div className="wal-card__row">
        <div><div className="wal-card__value">{value}</div><div className="wal-card__delta">{delta}</div></div>
        <Sparkline values={spark} color={navy ? "#ffd23f" : "#00338d"} />
      </div>
    </div>
  );
}

const arrow = (n: number) => (n >= 0 ? "▲" : "▼");

export default function WalletScreen() {
  // The selected line, ledger filter and page live in the URL. The Top-Up button on a line links here with ?line=.
  const [params, setParams] = useSearchParams();
  const line = params.get("line");
  const kind: LedgerTab = isTab(params.get("kind")) ? (params.get("kind") as LedgerTab) : "all";
  const page = Math.max(1, Number(params.get("page")) || 1);

  const summary = useQuery({ queryKey: ["wallet", "summary"], queryFn: getWalletSummary, refetchInterval: 60_000 });
  const ledger = useQuery({ queryKey: ["ledger", { line, kind, page }], queryFn: () => getLedger({ line, kind, page, pageSize: PAGE_SIZE }), placeholderData: keepPreviousData });

  const go = (next: { line?: string | null; kind?: LedgerTab; page?: number }) => {
    const nl = next.line === undefined ? line : next.line, nk = next.kind ?? kind, np = next.page ?? 1; // a new line or filter goes back to page 1
    const p = new URLSearchParams();
    if (nl) p.set("line", nl);
    if (nk !== "all") p.set("kind", nk);
    if (np > 1) p.set("page", String(np));
    setParams(p, { replace: true });
  };

  const s = summary.data;
  const total = ledger.data?.total ?? 0, last = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1, to = Math.min(page * PAGE_SIZE, total);
  const thousands = (kobo: number) => Math.round(kobo / 100 / 100) / 10; // naira in thousands, one decimal

  return (
    <div className="wal">
      <div>
        <h1>Wallet &amp; Ledger</h1>
        <p className="muted" style={{ marginTop: 4 }}>Each line has its own wallet. The ledger is append-only: a correction is a new entry, never an edit.</p>
      </div>

      <LineFinder onPick={(imsi) => go({ line: imsi })} />

      <div className="wal-cards">
        {s ? (
          <>
            <SummaryCard navy label="Sum of all line wallets" value={formatNaira(s.totalBalanceKobo)} delta={`${arrow(s.balanceTrendKobo[6] - s.balanceTrendKobo[0])} ${formatNaira(Math.abs(s.balanceTrendKobo[6] - s.balanceTrendKobo[0]))} this week`} spark={s.balanceTrendKobo} />
            <SummaryCard label="Wallets with a balance" value={formatCount(s.walletsWithBalance)} delta={`${arrow(s.walletsTrend[6] - s.walletsTrend[0])} ${Math.abs(s.walletsTrend[6] - s.walletsTrend[0])} this week`} spark={s.walletsTrend} />
            <SummaryCard label="Ledger entries today" value={formatCount(s.entriesToday)} delta="Since 00:00 WAT" spark={s.entriesTrend} />
          </>
        ) : summary.isError ? (
          <div className="card wal-message">Could not load the summary. <button type="button" className="btn btn--sm" onClick={() => summary.refetch()}>Try again</button></div>
        ) : (
          [0, 1, 2].map((i) => <div key={i} className="card skeleton" style={{ height: 110 }} aria-busy="true" />)
        )}
      </div>

      {line && <LineWalletCard key={line} imsi={line} onClear={() => go({ line: null })} />}

      <div className="wal-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={kind === t.key} className={kind === t.key ? "on" : ""} onClick={() => go({ kind: t.key })}>
            {t.label}{ledger.data ? ` (${formatCount(ledger.data.counts[t.key])})` : ""}
          </button>
        ))}
      </div>

      <div className={line ? "" : "wal-grid"}>
        <section className="card wal-ledger">
          {ledger.isError ? (
            <div className="wal-message">Could not load the ledger. <button type="button" className="btn btn--sm" onClick={() => ledger.refetch()}>Try again</button></div>
          ) : (
            <table className="data-table">
              <thead><tr><th>Entry ID</th><th>Line ID</th><th>Amount (kobo)</th><th>Entry type</th><th>Reference ID</th><th>Created (WAT)</th></tr></thead>
              <tbody>
                {ledger.isPending && <tr><td colSpan={6} className="muted">Loading...</td></tr>}
                {ledger.data?.items.map((e) => (
                  <tr key={e.entryId}>
                    <td>{e.entryId}</td>
                    <td><Link className="wal-link" to={`/lines/${e.imsi}`} title={e.msisdn}>{e.lineId}</Link></td>
                    <td><Amount kobo={e.amountKobo} /></td>
                    <td><Badge tone={KIND_TONE[e.kind]}>{e.kind}</Badge></td>
                    <td>{e.reference}</td>
                    <td>{formatWAT(e.createdAt)}</td>
                  </tr>
                ))}
                {ledger.data && ledger.data.items.length === 0 && <tr><td colSpan={6} className="muted">No entries here.</td></tr>}
              </tbody>
            </table>
          )}
          <div className="wal-footer">
            <span className="muted">Showing {from} to {to} of {formatCount(total)} entries</span>
            <div className="wal-pages">
              <button type="button" className="chip" disabled={page <= 1} onClick={() => go({ page: page - 1 })}>Previous</button>
              <span className="muted">Page {page} of {last}</span>
              <button type="button" className="chip" disabled={page >= last} onClick={() => go({ page: page + 1 })}>Next</button>
            </div>
          </div>
        </section>

        {!line && s && (
          <section className="card">
            <h3>Money in and out (₦ thousands)</h3>
            <GroupedBarChart a={s.daily.map((d) => thousands(d.inKobo))} b={s.daily.map((d) => thousands(d.outKobo))} labels={s.daily.map((d) => weekdayShort(d.date))} />
            <div className="wal-legend">
              <span><i style={{ background: "#00338d" }} />Money in</span>
              <span><i style={{ background: "#ffcc00" }} />Money out</span>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
