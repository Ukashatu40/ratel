import { useId } from "react";

type Pt = [number, number];
// Smooth line through points using cubic curves with horizontal control handles.
function smooth(pts: Pt[]) {
  let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    const cx = (x0 + x1) / 2;
    d += ` C${cx.toFixed(1)},${y0.toFixed(1)} ${cx.toFixed(1)},${y1.toFixed(1)} ${x1.toFixed(1)},${y1.toFixed(1)}`;
  }
  return d;
}

export function Sparkline({ values, color, width = 130, height = 42 }: { values: number[]; color: string; width?: number; height?: number }) {
  const max = Math.max(...values), min = Math.min(...values), span = max - min || 1;
  const pts: Pt[] = values.map((v, i) => [2 + (i * (width - 4)) / (values.length - 1), height - 5 - ((v - min) / span) * (height - 10)]);
  return (
    <svg width={width} height={height} aria-hidden="true">
      <path d={smooth(pts)} fill="none" stroke={color} strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

interface AreaProps { values: number[]; labels: string[]; formatTick: (n: number) => string; color?: string; width?: number; height?: number }
export function AreaChart({ values, labels, formatTick, color = "#00338d", width = 1000, height = 200 }: AreaProps) {
  const gid = useId().replace(/:/g, "");
  const L = 52, R = 16, T = 14, B = 34;
  const pw = width - L - R, ph = height - T - B, max = Math.max(...values) * 1.2;
  const pts: Pt[] = values.map((v, i) => [L + (i * pw) / (values.length - 1), T + ph - (v / max) * ph]);
  const line = smooth(pts);
  const [lx, ly] = pts[pts.length - 1];
  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: "auto" }} role="img" aria-label="Area chart">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity=".28" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0, 1, 2, 3, 4].map((k) => {
        const y = T + (ph * k) / 4;
        return (
          <g key={k}>
            <line x1={L} x2={width - R} y1={y} y2={y} stroke="#e6ecf4" />
            <text x={L - 10} y={y + 4} textAnchor="end" fontSize="12" fill="#64748b">{formatTick(max * (1 - k / 4))}</text>
          </g>
        );
      })}
      <path d={`${line} L${lx.toFixed(1)},${T + ph} L${pts[0][0].toFixed(1)},${T + ph} Z`} fill={`url(#${gid})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" />
      <circle cx={lx} cy={ly} r="6" fill="#fff" stroke={color} strokeWidth="3" />
      {pts.map(([x], i) => <text key={i} x={x} y={height - 10} textAnchor="middle" fontSize="12" fill="#64748b">{labels[i]}</text>)}
    </svg>
  );
}

export interface DonutPart { value: number; color: string }
export function DonutChart({ parts, centerValue, centerLabel, size = 190, thickness = 26 }: { parts: DonutPart[]; centerValue: string; centerLabel: string; size?: number; thickness?: number }) {
  const r = (size - thickness) / 2, c = 2 * Math.PI * r, m = size / 2;
  const total = parts.reduce((s, p) => s + p.value, 0);
  return (
    <svg width={size} height={size} role="img" aria-label="Donut chart">
      {parts.map((p, i) => {
        const len = (p.value / total) * c, seg = Math.max(len - 4, 1);
        const offset = (parts.slice(0, i).reduce((s, q) => s + q.value, 0) / total) * c; // where this arc starts
        return <circle key={p.color} cx={m} cy={m} r={r} fill="none" stroke={p.color} strokeWidth={thickness} strokeDasharray={`${seg} ${c - seg}`} strokeDashoffset={-offset} transform={`rotate(-90 ${m} ${m})`} />;
      })}
      <text x={m} y={m + 4} textAnchor="middle" fontSize="30" fontWeight="700" fill="#0f2038">{centerValue}</text>
      <text x={m} y={m + 26} textAnchor="middle" fontSize="13" fill="#64748b">{centerLabel}</text>
    </svg>
  );
}

// A single progress ring, e.g. how much of a data allowance is used.
export function RingChart({ fraction, label, sub, color = "#00338d", size = 150, thickness = 15 }: { fraction: number; label: string; sub: string; color?: string; size?: number; thickness?: number }) {
  const r = (size - thickness) / 2, c = 2 * Math.PI * r, m = size / 2, f = Math.min(Math.max(fraction, 0), 1);
  return (
    <svg width={size} height={size} role="img" aria-label={`${label} ${sub}`}>
      <circle cx={m} cy={m} r={r} fill="none" stroke="#e8effc" strokeWidth={thickness} />
      <circle cx={m} cy={m} r={r} fill="none" stroke={color} strokeWidth={thickness} strokeLinecap="round" strokeDasharray={`${c * f} ${c}`} transform={`rotate(-90 ${m} ${m})`} />
      <text x={m} y={m + 8} textAnchor="middle" fontSize="28" fontWeight="700" fill="#0f2038">{label}</text>
      <text x={m} y={m + 28} textAnchor="middle" fontSize="12" fill="#64748b">{sub}</text>
    </svg>
  );
}

// Simple bars; the last one (today) is highlighted.
export function BarChart({ values, labels, width = 760, height = 200 }: { values: number[]; labels: string[]; width?: number; height?: number }) {
  const L = 10, T = 14, B = 30, max = Math.max(...values, 0.0001) * 1.15, ph = height - T - B, gw = (width - 2 * L) / values.length, bw = gw * 0.62;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: "auto" }} role="img" aria-label="Bar chart">
      <line x1={L} x2={width - L} y1={T + ph} y2={T + ph} stroke="#e6ecf4" />
      {values.map((v, i) => {
        const h = (v / max) * ph, x = L + i * gw + gw * 0.19;
        return (
          <g key={i}>
            <rect x={x} y={T + ph - h} width={bw} height={h} rx="5" fill={i === values.length - 1 ? "#00338d" : "#c9d6f0"} />
            <text x={L + i * gw + gw / 2} y={height - 9} textAnchor="middle" fontSize="12" fill="#64748b">{labels[i]}</text>
          </g>
        );
      })}
    </svg>
  );
}

// Two series side by side per label, e.g. money in and money out per day.
export function GroupedBarChart({ a, b, labels, width = 520, height = 250, colors = ["#00338d", "#ffcc00"] }: { a: number[]; b: number[]; labels: string[]; width?: number; height?: number; colors?: [string, string] | string[] }) {
  const L = 10, T = 14, B = 30, max = Math.max(...a, ...b, 0.0001) * 1.15, ph = height - T - B, gw = (width - 2 * L) / labels.length, bw = (gw * 0.62) / 2;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: "auto" }} role="img" aria-label="Grouped bar chart">
      <line x1={L} x2={width - L} y1={T + ph} y2={T + ph} stroke="#e6ecf4" />
      {labels.map((label, j) => (
        <g key={j}>
          {[a[j], b[j]].map((v, i) => {
            const h = (v / max) * ph;
            return <rect key={i} x={L + j * gw + gw * 0.19 + i * bw} y={T + ph - h} width={bw - 2} height={h} rx="5" fill={colors[i]} />;
          })}
          <text x={L + j * gw + gw / 2} y={height - 9} textAnchor="middle" fontSize="12" fill="#64748b">{label}</text>
        </g>
      ))}
    </svg>
  );
}
