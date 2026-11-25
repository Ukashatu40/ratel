import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { formatNaira } from "../../lib/format";
import { getSettings, saveSettings } from "./api";
import type { CatalogueSettings, SettingsView } from "./types";

// Airtime limits and call rates (docs/catalogue.md). Typed in naira, kept in whole kobo.
interface Form { airtimeMin: string; cardMin: string; cardMax: string; presets: string; onnet: string; offnet: string; reason: string }

const naira = (kobo: number) => (kobo / 100).toFixed(2).replace(/\.00$/, "");
const toForm = (s: CatalogueSettings): Form => ({
  airtimeMin: naira(s.airtimeMinKobo), cardMin: naira(s.cardMinKobo), cardMax: naira(s.cardMaxKobo),
  presets: s.presetsKobo.map(naira).join(", "), onnet: naira(s.onnetKoboPerMin), offnet: naira(s.offnetKoboPerMin), reason: "",
});
const kobo = (text: string): number | null => (/^\d+(\.\d{1,2})?$/.test(text.trim()) ? Math.round(Number(text) * 100) : null);

function build(f: Form, gateway: { minKobo: number; maxKobo: number }): { value: CatalogueSettings | null; error: string } {
  const airtimeMinKobo = kobo(f.airtimeMin), cardMinKobo = kobo(f.cardMin), cardMaxKobo = kobo(f.cardMax);
  const onnet = kobo(f.onnet), offnet = kobo(f.offnet);
  const presets = f.presets.split(",").map((p) => p.trim()).filter(Boolean).map(kobo);
  if ([airtimeMinKobo, cardMinKobo, cardMaxKobo, onnet, offnet].some((v) => v === null) || presets.some((p) => p === null)) {
    return { value: null, error: "Enter amounts in naira, for example 20 or 2.50." };
  }
  const list = presets as number[];
  if ((airtimeMinKobo as number) < 1) return { value: null, error: "The smallest top-up must be more than zero." };
  if ((cardMinKobo as number) < gateway.minKobo) return { value: null, error: `The payment gateway takes no less than ${formatNaira(gateway.minKobo)} by card.` };
  if ((cardMaxKobo as number) > gateway.maxKobo) return { value: null, error: `The payment gateway takes no more than ${formatNaira(gateway.maxKobo)} by card.` };
  if ((cardMinKobo as number) < (airtimeMinKobo as number) || (cardMaxKobo as number) < (cardMinKobo as number)) return { value: null, error: "Check the order: smallest top-up, then card minimum, then card maximum." };
  if (list.length < 1 || list.length > 6) return { value: null, error: "Give between 1 and 6 airtime amounts for the menus." };
  if (list.some((p, i) => i > 0 && p <= list[i - 1])) return { value: null, error: "Airtime amounts must be different and smallest first." };
  if (list[0] < (cardMinKobo as number) || list[list.length - 1] > (cardMaxKobo as number)) return { value: null, error: "Every airtime amount must be within the card limits." };
  if (!f.reason.trim()) return { value: null, error: "Say why, for example: launch rates." };
  return {
    value: { airtimeMinKobo: airtimeMinKobo as number, cardMinKobo: cardMinKobo as number, cardMaxKobo: cardMaxKobo as number, presetsKobo: list, onnetKoboPerMin: onnet as number, offnetKoboPerMin: offnet as number },
    error: "",
  };
}

export function SettingsCard() {
  const view = useQuery({ queryKey: ["catalogue-settings"], queryFn: getSettings });
  if (view.isError) return <section className="card plans__card"><h3>Airtime &amp; calls</h3><p className="muted">Could not load the settings.</p></section>;
  if (!view.data) return <section className="card plans__card"><h3>Airtime &amp; calls</h3><p className="muted">Loading...</p></section>;
  return <SettingsForm view={view.data} />;
}

function SettingsForm({ view }: { view: SettingsView }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Form>(() => toForm(view.settings));
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const save = useMutation({
    mutationFn: ({ value, reason }: { value: CatalogueSettings; reason: string }) => saveSettings(value, reason),
    onSuccess: () => { setSaved(true); setForm((f) => ({ ...f, reason: "" })); void queryClient.invalidateQueries({ queryKey: ["catalogue-settings"] }); },
  });

  const gateway = view.gateway;
  const input = (k: keyof Form, label: string, hint?: string) => (
    <div className="field">
      <label htmlFor={`s-${k}`}>{label}</label>
      <input id={`s-${k}`} className="input" value={form[k]} onChange={(e) => { setSaved(false); setForm({ ...form, [k]: e.target.value }); }} inputMode={k === "presets" || k === "reason" ? "text" : "decimal"} />
      {hint && <span className="muted" style={{ fontSize: 12 }}>{hint}</span>}
    </div>
  );
  const submit = () => {
    const { value, error: found } = build(form, gateway);
    setError(found);
    if (value) save.mutate({ value, reason: form.reason.trim() });
  };

  return (
    <section className="card plans__card">
      <h3>Airtime &amp; calls <span className="muted plans__hint">amounts in naira</span></h3>
      <div style={{ padding: "0 20px 20px" }}>
      <div className="plans-form">
        {input("airtimeMin", "Smallest top-up (₦)", "Where no payment processor sets a floor")}
        {input("cardMin", "Card payment minimum (₦)", `Gateway floor ${formatNaira(gateway.minKobo)}`)}
        {input("cardMax", "Card payment maximum (₦)")}
        {input("presets", "Airtime amounts in the SMS and USSD menus (₦)", "Comma separated, smallest first, up to 6")}
        {input("onnet", "Calls to Ratelplus numbers (₦ per minute)", "Charged per second")}
        {input("offnet", "Calls to other networks (₦ per minute)", "Charged per second")}
        {input("reason", "Why the settings change (kept in the audit trail)")}
      </div>
      {(error || save.isError) && <div className="alert alert--danger" style={{ margin: "8px 0" }}>{error || save.error?.message}</div>}
      {saved && !save.isPending && <div className="alert alert--ok" style={{ margin: "8px 0" }}>Saved. New calls and top-ups use these values.</div>}
      <div className="plans-actions"><button type="button" className="btn" onClick={submit} disabled={save.isPending}>{save.isPending ? "Saving..." : "Save airtime & call settings"}</button></div>
      </div>
    </section>
  );
}
