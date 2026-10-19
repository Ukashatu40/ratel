import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { StateBadge } from "../../components/ui";
import { ApiError } from "../../lib/api";
import { initials } from "../../lib/format";
import { NEXT_ATTACH_NOTE } from "../../lib/messages";
import { SuspendDialog } from "../lines/SuspendDialog";
import type { LineRow } from "../lines/types";
import { getLine } from "./api";
import { CallsTab } from "./CallsTab";
import { HistoryTab } from "./HistoryTab";
import { OverviewTab } from "./OverviewTab";
import { UsageTab } from "./UsageTab";
import "./LineDetailScreen.css";

const TABS = [{ key: "overview", label: "Overview" }, { key: "usage", label: "Usage" }, { key: "calls", label: "Calls" }, { key: "history", label: "History" }] as const;
type TabKey = (typeof TABS)[number]["key"];
const isTab = (v: string | null): v is TabKey => TABS.some((t) => t.key === v);

export default function LineDetailScreen() {
  const { imsi = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab: TabKey = isTab(params.get("tab")) ? (params.get("tab") as TabKey) : "overview"; // the open tab lives in the URL
  const [suspending, setSuspending] = useState(false);
  const queryClient = useQueryClient();

  const { data: line, isPending, isError, error, refetch } = useQuery({
    queryKey: ["line", imsi],
    queryFn: () => getLine(imsi),
    retry: (count, e) => !(e instanceof ApiError && e.status === 404) && count < 1, // do not retry "not found"
  });

  if (isPending) return <div className="card skeleton" style={{ height: 160 }} aria-busy="true" />;
  if (isError) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="card ld-message">
        <b>{notFound ? "That line does not exist." : "The line could not be loaded."}</b>
        {!notFound && <button type="button" className="btn btn--sm" onClick={() => refetch()}>Try again</button>}
        <Link to="/lines" className="btn btn--outline btn--sm">Back to lines</Link>
      </div>
    );
  }

  const row: LineRow = { imsi: line.imsi, iccid: line.iccid, msisdn: line.msisdn, customerName: line.customerName, planName: line.planName, state: line.state, planEndsEpoch: line.planEndsEpoch };
  const canSuspend = line.state === "active" || line.state === "out_of_data"; // from the line state machine
  const setTab = (t: TabKey) => setParams(t === "overview" ? {} : { tab: t }, { replace: true });

  return (
    <div className="ld">
      <Link to="/lines" className="ld-back">← Back to lines</Link>
      <div className="ld-head">
        <span className="ld-avatar">{initials(line.customerName)}</span>
        <div>
          <h1>{line.msisdn} <StateBadge state={line.state} /></h1>
          <p className="muted">{line.customerName} &nbsp;|&nbsp; {line.planName} &nbsp;|&nbsp; IMSI {line.imsi}</p>
        </div>
        <div className="ld-actions">
          <Link to={`/finance/wallet?line=${line.imsi}`} className="btn btn--outline">Top-Up</Link>
          <button type="button" className="btn btn--danger" disabled={!canSuspend} onClick={() => setSuspending(true)}>Suspend line</button>
        </div>
      </div>

      <div className="alert alert--warn">{NEXT_ATTACH_NOTE}</div>

      <div className="ld-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} className={tab === t.key ? "on" : ""} onClick={() => setTab(t.key)}>{t.label}</button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab line={line} />}
      {tab === "usage" && <UsageTab imsi={line.imsi} />}
      {tab === "calls" && <CallsTab imsi={line.imsi} />}
      {tab === "history" && <HistoryTab imsi={line.imsi} />}

      {suspending && (
        <SuspendDialog line={row} onClose={() => { setSuspending(false); void queryClient.invalidateQueries({ queryKey: ["line", imsi] }); }} />
      )}
    </div>
  );
}