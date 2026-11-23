import { Badge, type Tone } from "../../components/ui";
import { BarChart, RingChart } from "../../components/charts/charts";
import { formatGB1, formatWAT, weekdayShort } from "../../lib/format";
import type { LineDetail } from "./types";

const PROVISIONING: Record<LineDetail["provisioning"], [Tone, string]> = { active: ["green", "Active"], provisioned: ["amber", "Not in service"], barred: ["red", "Barred"], unknown: ["grey", "Not available yet"] };
const NETWORK: Record<LineDetail["networkCheck"], [Tone, string]> = { matches: ["green", "Matches RatelLink"], mismatch: ["red", "Does not match"], unknown: ["grey", "Not checked"] };

// How much of the allowance is used. When RatelBSS does not say (no plan start yet), out of data still means all of it, and an
// active line shows that the figure is not available instead of a false 0%.
function allowanceView(line: LineDetail): { fraction: number; label: string; sub: string; text: string } {
  const total = formatGB1(line.allowanceTotalBytes);
  if (line.allowanceUsedBytes === null) {
    return line.state === "out_of_data"
      ? { fraction: 1, label: "100%", sub: "used", text: `${total} plan, used up` }
      : { fraction: 0, label: "–", sub: "not available yet", text: `${total} plan` };
  }
  const fraction = line.allowanceTotalBytes ? line.allowanceUsedBytes / line.allowanceTotalBytes : 0;
  return { fraction, label: `${Math.round(fraction * 100)}%`, sub: "used", text: `${formatGB1(line.allowanceUsedBytes)} of ${total}` };
}

const validityText = (planEndsEpoch: number | null, state: LineDetail["state"]): string =>
  planEndsEpoch ? `Valid until ${formatWAT(planEndsEpoch)}` : state === "awaiting_activation" ? "Not started" : "Valid until: not available yet";

export function OverviewTab({ line }: { line: LineDetail }) {
  const allowance = allowanceView(line);
  const used = allowance.fraction >= 1;
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
          <RingChart fraction={allowance.fraction} label={allowance.label} sub={allowance.sub} color={used ? "#e4002b" : "#00338d"} />
          <b>{allowance.text}</b>
          <div className="muted">{validityText(line.planEndsEpoch, line.state)}</div>
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