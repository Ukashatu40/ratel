import { Sparkline } from "../../components/charts/charts";

export function StatCard({ label, value, delta, note, spark }: { label: string; value: string; delta: string; note?: string; spark: number[] }) {
  return (
    <div className="card rep-stat">
      <div className="muted">{label}</div>
      <div className="rep-stat__row">
        <div>
          <div className="rep-stat__value">{value}</div>
          <div className="rep-stat__delta">{delta}</div>
          {note && <div className="rep-stat__delta">{note}</div>}
        </div>
        <Sparkline values={spark} color="#00338d" />
      </div>
    </div>
  );
}
