import type { ReactNode } from "react";
import { Icon, type IconName } from "../../components/ui";
import { Sparkline } from "../../components/charts/charts";

type Tone = "green" | "red" | "amber" | "navy";
const SPARK: Record<Tone, string> = { green: "#008751", red: "#e4002b", amber: "#c99700", navy: "#ffd23f" };

interface Props { label: string; value: string; badge: ReactNode; delta: string; spark: number[]; icon: IconName; tone: Tone }
export function KpiCard({ label, value, badge, delta, spark, icon, tone }: Props) {
  return (
    <div className={`card kpi kpi--${tone}`}>
      <div className="kpi__top">
        <div className="kpi__icon"><Icon name={icon} /></div>
        <div className="kpi__label">{label}</div>
        {badge}
      </div>
      <div className="kpi__bottom">
        <div>
          <div className="kpi__value">{value}</div>
          <div className="kpi__delta">{delta}</div>
        </div>
        <Sparkline values={spark} color={SPARK[tone]} />
      </div>
    </div>
  );
}