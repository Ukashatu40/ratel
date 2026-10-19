import type { ReactNode } from "react";
import type { LineState } from "../screens/dashboard/types";
import type { KycStatus } from "../screens/sell-sim/types";

export type Tone = "green" | "red" | "amber" | "blue" | "grey";
export const Badge = ({ tone, children }: { tone: Tone; children: ReactNode }) => <span className={`badge badge--${tone}`}>{children}</span>;

// Colour rules from the design: active green; out_of_data and expired red; awaiting_activation and suspended amber.
const STATE_TONE: Record<LineState, Tone> = { active: "green", out_of_data: "red", expired: "red", awaiting_activation: "amber", suspended: "amber", terminated: "grey" };
export const StateBadge = ({ state }: { state: LineState }) => <Badge tone={STATE_TONE[state]}>{state}</Badge>;

const ICONS = {
  dashboard: <><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></>,
  sim: <><path d="M6 3h8l4 4v14H6z" /><rect x="9" y="12" width="6" height="6" rx="1" /></>,
  lines: <path d="M4 20v-4M9 20v-8M14 20V8M19 20V4" />,
  customers: <><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" /></>,
  plans: <><path d="M12 3l9 5-9 5-9-5z" /><path d="M3 13l9 5 9-5" /></>,
  stock: <><path d="M3 8l9-5 9 5v9l-9 5-9-5z" /><path d="M3 8l9 5 9-5M12 13v9" /></>,
  wallet: <><rect x="3" y="6" width="18" height="14" rx="3" /><path d="M3 10h18" /><circle cx="16.5" cy="15" r="1.2" /></>,
  reports: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  staff: <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />,
};
export type IconName = keyof typeof ICONS;
export const Icon = ({ name }: { name: IconName }) => (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONS[name]}</svg>
);

const KYC_TONE: Record<KycStatus, Tone> = { verified: "green", pending: "amber", rejected: "red" };
export const KycBadge = ({ status }: { status: KycStatus }) => <Badge tone={KYC_TONE[status]}>{status[0].toUpperCase() + status.slice(1)}</Badge>;
