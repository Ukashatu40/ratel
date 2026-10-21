import { Badge, type Tone } from "../../components/ui";
import { BarChart, RingChart } from "../../components/charts/charts";
import { formatGB1, formatWAT, weekdayShort } from "../../lib/format";
import type { LineDetail } from "./types";

const PROVISIONING: Record<LineDetail["provisioning"], [Tone, string]> = { active: ["green", "Active"], provisioned: ["amber", "Not in service"], barred: ["red", "Barred"] };
const NETWORK: Record<LineDetail["networkCheck"], [Tone, string]> = { matches: ["green", "Matches RatelLink"], mismatch: ["red", "Does not match"], unknown: ["grey", "Not checked"] };

export function OverviewTab({ line }: { line: LineDetail }) {
  const fraction = line.allowanceTotalBytes ? line.allowanceUsedBytes / line.allowanceTotalBytes : 0;
  const used = fraction >= 1;
  const [pTone, pText] = PROVISIONING[line.provisioning];
  const [nTone, nText] = NETWORK[line.networkCheck];
  return (
    <>
      {line.state === "out_of_data" && (
        <div className="ld-info">The data allowance is used up, so the internet is slowed or off. Calls still work. Buying a bundle or a new plan returns the line to active.</div>
      )}
      <div className="ld-grid">
        <section className="card ld-ring">
          <div className="muted ld-left">Data allowance</div>
          <RingChart fraction={fraction} label={`${Math.round(fraction * 100)}%`} sub="used" color={used ? "#e4002b" : "#00338d"} />
          <b>{formatGB1(line.allowanceUsedBytes)} of {formatGB1(line.allowanceTotalBytes)}</b>
          <div className="muted">{line.planEndsEpoch ? `Valid until ${formatWAT(line.planEndsEpoch)}` : "Not started"}</div>
        </section>
        <section className="card">
          <h3>Data used per day (GB)</h3>
          <BarChart values={line.dailyUsage.map((d) => Math.round(d.bytes / 1e7) / 100)} labels={line.dailyUsage.map((d) => weekdayShort(d.date))} />
        </section>
        <section className="card">
          <h3>Line profile</h3>
          <div className="ld-kv"><span>Speed profile</span><span>{line.speedUlMbps} up / {line.speedDlMbps} down Mbps</span></div>
          <div className="ld-kv"><span>Static IP address</span><span>{line.staticIp ?? "Not assigned yet"}</span></div>
          <div className="ld-kv"><span>Provisioning</span><Badge tone={pTone}>{pText}</Badge></div>
          <div className="ld-kv"><span>Network check</span><Badge tone={nTone}>{nText}</Badge></div>
        </section>
      </div>
    </>
  );
}