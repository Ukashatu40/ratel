import { Link, useSearchParams } from "react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Badge, type Tone } from "../../components/ui";
import { GroupedBarChart, Sparkline } from "../../components/charts/charts";
import { formatCount, formatMsisdn, formatNaira, formatWAT, weekdayShort } from "../../lib/format";
import { getLedger, getWalletSummary } from "./api";
import { LineFinder } from "./LineFinder";
import { LineWalletCard } from "./LineWalletCard";
import { KIND_LABEL, KNOWN_KINDS, type LedgerTab } from "./types";
import "./WalletScreen.css";

const PAGE_SIZE = 10;
const KIND_TONE: Record<string, Tone> = { top_up: "green", purchase: "blue", vat: "grey", correction: "amber" };
// The tabs are "All", the kinds we know, and any other kind the API reports.
const tabsFor = (counts: Record<string, number> | undefined): { key: LedgerTab; label: string }[] => {
  const extra = Object.keys(counts ?? {}).filter((k) => k !== "all" && !KNOWN_KINDS.includes(k));
  return [{ key: "all", label: "All" }, ...[...KNOWN_KINDS, ...extra].map((k) => ({ key: k, label: KIND_LABEL[k] ?? k }))];
};

// +350,000 (₦3,500.00): the kobo value is what is stored, the naira value is for reading.
function Amount({ kobo }: { kobo: number }) {
  return (
    <span>
      <b className={kobo >= 0 ? "wal-in" : "wal-out"}>{kobo >= 0 ? "+" : "-"}{formatCount(Math.abs(kobo))}</b>{" "}
      <span className="muted">({formatNaira(Math.abs(kobo))})</span>
    </span>
  );
}

function SummaryCard({ label, value, delta, spark, navy }: { label: string; value: string; delta?: string; spark?: number[]; navy?: boolean }) {
  return (
    <div className={`card wal-card${navy ? " wal-card--navy" : ""}`}>
      <div className="wal-card__label">{label}</div>
      <div className="wal-card__row">
        <div><div className="wal-card__value">{value}</div>{delta && <div className="wal-card__delta">{delta}</div>}</div>
        {spark && <Sparkline values={spark} color={navy ? "#ffd23f" : "#00338d"} />}
      </div>
    </div>
  );
}

const arrow = (n: number) => (n >= 0 ? "▲" : "▼");

export default function WalletScreen() {
  // The selected line, ledger filter and page live in the URL. The Top-Up button on a line links here with ?line=.
  const [params, setParams] = useSearchParams();
  const line = params.get("line");
  const kind: LedgerTab = params.get("kind") || "all";
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

      <LineFinder onPick={(lineId) => go({ line: lineId })} />

      <div className="wal-cards">
        {s ? (
          <>
            <SummaryCard navy label="Sum of all line wallets" value={formatNaira(s.totalBalanceKobo)} delta={s.trends ? `${arrow(s.trends.balance[6] - s.trends.balance[0])} ${formatNaira(Math.abs(s.trends.balance[6] - s.trends.balance[0]))} this week` : undefined} spark={s.trends?.balance} />
            <SummaryCard label="Wallets with a balance" value={formatCount(s.walletsWithBalance)} delta={s.trends ? `${arrow(s.trends.wallets[6] - s.trends.wallets[0])} ${Math.abs(s.trends.wallets[6] - s.trends.wallets[0])} this week` : undefined} spark={s.trends?.wallets} />
            <SummaryCard label="Ledger entries today" value={formatCount(s.entriesToday)} delta="Since 00:00 WAT" spark={s.trends?.entries} />
          </>
        ) : summary.isError ? (
          <div className="card wal-message">Could not load the summary. <button type="button" className="btn btn--sm" onClick={() => summary.refetch()}>Try again</button></div>
        ) : (
          [0, 1, 2].map((i) => <div key={i} className="card skeleton" style={{ height: 110 }} aria-busy="true" />)
        )}
      </div>

      {line && <LineWalletCard key={line} lineKey={line} onClear={() => go({ line: null })} />}

      <div className="wal-tabs" role="tablist">
        {tabsFor(ledger.data?.counts).map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={kind === t.key} className={kind === t.key ? "on" : ""} onClick={() => go({ kind: t.key })}>
            {t.label}{ledger.data ? ` (${formatCount(ledger.data.counts[t.key] ?? 0)})` : ""}
          </button>
        ))}
      </div>

      <div className={line ? "" : "wal-grid"}>
        <section className="card wal-ledger">
          {ledger.isError ? (
            <div className="wal-message">Could not load the ledger. <button type="button" className="btn btn--sm" onClick={() => ledger.refetch()}>Try again</button></div>
          ) : (
            <table className="data-table">
              <thead><tr><th>Entry ID</th><th>Line</th><th>Amount (kobo)</th><th>Entry type</th><th>Reference</th><th>Created (WAT)</th></tr></thead>
              <tbody>
                {ledger.isPending && <tr><td colSpan={6} className="muted">Loading...</td></tr>}
                {ledger.data?.items.map((e) => (
                  <tr key={e.entryId}>
                    <td>{e.entryId}</td>
                    <td><Link className="wal-link" to={`/lines/${e.lineId}`}>{formatMsisdn(e.msisdn)}</Link></td>
                    <td><Amount kobo={e.amountKobo} /></td>
                    <td><Badge tone={KIND_TONE[e.kind] ?? "grey"}>{KIND_LABEL[e.kind] ?? e.kind}</Badge></td>
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
