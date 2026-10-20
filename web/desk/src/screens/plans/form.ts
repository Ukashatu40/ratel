import type { BundleInput, Bundle, Kind, PlanFull, PlanInput } from "./types";

// The drawer works with text fields. These helpers convert to and from the real values
// (price in whole kobo, data in bytes) and check the input.
export interface FormState {
  name: string; price: string; validity: string; dataGb: string;
  ul: string; dl: string; exhaustion: "slow" | "stop"; slowUl: string; slowDl: string; channels: string[];
}
export type Errors = Partial<Record<keyof FormState, string>>;

export const emptyForm = (): FormState => ({ name: "", price: "", validity: "", dataGb: "", ul: "", dl: "", exhaustion: "slow", slowUl: "0.5", slowDl: "1", channels: ["RatelDesk", "RatelPay"] });
export const planToForm = (p: PlanFull): FormState => ({
  name: p.name, price: (p.priceKobo / 100).toFixed(2), validity: String(p.validityDays), dataGb: String(p.dataBytes / 1e9),
  ul: String(p.speedUlMbps), dl: String(p.speedDlMbps), exhaustion: p.onExhaustion, slowUl: String(p.slowUlMbps), slowDl: String(p.slowDlMbps), channels: p.channels,
});
export const bundleToForm = (b: Bundle): FormState => ({ ...emptyForm(), name: b.name, price: (b.priceKobo / 100).toFixed(2), validity: String(b.validityDays), dataGb: String(b.dataBytes / 1e9), channels: b.channels });

const decimal = (s: string) => (/^\d+(\.\d+)?$/.test(s.trim()) ? Number(s) : null);
const wholeKobo = (s: string) => (/^\d+(\.\d{1,2})?$/.test(s.trim()) ? Math.round(Number(s) * 100) : null); // never keep naira as a decimal

function common(f: FormState, errors: Errors) {
  const priceKobo = wholeKobo(f.price), validityDays = /^\d+$/.test(f.validity.trim()) ? Number(f.validity) : null, gb = decimal(f.dataGb);
  if (!f.name.trim()) errors.name = "Enter a name";
  if (priceKobo === null || priceKobo <= 0) errors.price = "Enter a price, for example 3500.00";
  if (validityDays === null || validityDays < 1) errors.validity = "Enter whole days, at least 1";
  if (gb === null || gb <= 0) errors.dataGb = "Enter the data in GB, for example 5";
  if (f.channels.length === 0) errors.channels = "Choose at least one channel";
  return { priceKobo: priceKobo ?? 0, validityDays: validityDays ?? 0, dataBytes: Math.round((gb ?? 0) * 1e9) };
}

export function build(kind: Kind, f: FormState): { errors: Errors; value: PlanInput | BundleInput | null } {
  const errors: Errors = {};
  const c = common(f, errors);
  const base = { name: f.name.trim(), ...c, channels: f.channels };
  if (kind === "bundle") return { errors, value: Object.keys(errors).length ? null : base };
  const ul = decimal(f.ul), dl = decimal(f.dl), sUl = decimal(f.slowUl), sDl = decimal(f.slowDl);
  if (ul === null || ul <= 0) errors.ul = "Enter the upload speed in Mbps";
  if (dl === null || dl <= 0) errors.dl = "Enter the download speed in Mbps";
  if (f.exhaustion === "slow") {
    if (sUl === null || sUl <= 0) errors.slowUl = "Enter the slow upload speed";
    if (sDl === null || sDl <= 0) errors.slowDl = "Enter the slow download speed";
  }
  const value: PlanInput = { ...base, speedUlMbps: ul ?? 0, speedDlMbps: dl ?? 0, onExhaustion: f.exhaustion, slowUlMbps: f.exhaustion === "slow" ? (sUl ?? 0) : 0, slowDlMbps: f.exhaustion === "slow" ? (sDl ?? 0) : 0 };
  return { errors, value: Object.keys(errors).length ? null : value };
}
