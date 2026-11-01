import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { StateBadge } from "../../components/ui";
import { ApiError } from "../../lib/api";
import { formatMsisdn, initials } from "../../lib/format";
import { useCurrentUser } from "../../lib/useCurrentUser";
import { NEXT_ATTACH_NOTE } from "../../lib/messages";
import { CareDialog } from "../lines/CareDialog";
import type { CareKind } from "../lines/types";
import { getLine } from "./api";
import { CallsTab } from "./CallsTab";
import { ContinueSale } from "./ContinueSale";
import { HistoryTab } from "./HistoryTab";
import { OverviewTab } from "./OverviewTab";
import { UsageTab } from "./UsageTab";
import "./LineDetailScreen.css";

const TABS = [{ key: "overview", label: "Overview" }, { key: "usage", label: "Usage" }, { key: "calls", label: "Calls" }, { key: "history", label: "History" }] as const;
type TabKey = (typeof TABS)[number]["key"];
const isTab = (v: string | null): v is TabKey => TABS.some((t) => t.key === v);

export default function LineDetailScreen() {
  const { lineId = "" } = useParams(); // the line's id in the API
  const user = useCurrentUser();
  const [params, setParams] = useSearchParams();
  const tab: TabKey = isTab(params.get("tab")) ? (params.get("tab") as TabKey) : "overview"; // the open tab lives in the URL
  const [acting, setActing] = useState<CareKind | null>(null);
  const queryClient = useQueryClient();

  const { data: line, isPending, isError, error, refetch } = useQuery({
    queryKey: ["line", lineId],
    queryFn: () => getLine(lineId),
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

  // From the line state machine: suspend from active or out_of_data, reinstate from suspended, terminate from any state
  // but terminated (and only an admin may terminate).
  const canSuspend = line.state === "active" || line.state === "out_of_data";
  const canReinstate = line.state === "suspended";
  const canTerminate = user.role === "Super Admin" && line.state !== "terminated";
  const setTab = (t: TabKey) => setParams(t === "overview" ? {} : { tab: t }, { replace: true });

  return (
    <div className="ld">
      <Link to="/lines" className="ld-back">← Back to lines</Link>
      <div className="ld-head">
        <span className="ld-avatar">{initials(line.customerName)}</span>
        <div>
          <h1>{formatMsisdn(line.msisdn)} <StateBadge state={line.state} /></h1>
          <p className="muted">{line.customerName} &nbsp;|&nbsp; {line.planName} &nbsp;|&nbsp; IMSI {line.imsi}</p>
        </div>
        <div className="ld-actions">
          <Link to={`/finance/wallet?line=${line.lineId}`} className="btn btn--outline">Top-Up</Link>
          {canReinstate
            ? <button type="button" className="btn" onClick={() => setActing("reinstate")}>Reinstate line</button>
            : <button type="button" className="btn btn--danger" disabled={!canSuspend} onClick={() => setActing("suspend")}>Suspend line</button>}
          {canTerminate && <button type="button" className="btn btn--outline" onClick={() => setActing("terminate")}>Terminate line</button>}
        </div>
      </div>

      <div className="alert alert--warn">{NEXT_ATTACH_NOTE}</div>

      <div className="ld-tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} className={tab === t.key ? "on" : ""} onClick={() => setTab(t.key)}>{t.label}</button>
        ))}
      </div>

      {line.state === "awaiting_activation" && <ContinueSale line={line} />}

      {tab === "overview" && <OverviewTab line={line} />}
      {tab === "usage" && <UsageTab lineKey={lineId} />}
      {tab === "calls" && <CallsTab lineKey={lineId} />}
      {tab === "history" && <HistoryTab lineKey={lineId} />}

      {acting && (
        <CareDialog kind={acting} line={line} onClose={() => { setActing(null); void queryClient.invalidateQueries({ queryKey: ["line", lineId] }); }} />
      )}
    </div>
  );
}