import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KycBadge } from "../../components/ui";
import { newIdempotencyKey } from "../../lib/api";
import { formatWAT, maskNin } from "../../lib/format";
import { getCustomer, getCustomerHistory, setKyc } from "./api";

// The KYC verification drawer: look at the submitted details, then approve or reject.
export function CustomerDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const panel = useRef<HTMLElement>(null);
  const [tab, setTab] = useState<"details" | "history">("details");
  const [reason, setReason] = useState("");
  const [key] = useState(newIdempotencyKey); // one key per decision, so a retry cannot record it twice

  const customer = useQuery({ queryKey: ["customer", id], queryFn: () => getCustomer(id) });
  const history = useQuery({ queryKey: ["customer", id, "history"], queryFn: () => getCustomerHistory(id) });

  const decide = useMutation({
    mutationFn: (status: "verified" | "rejected") => setKyc(id, { status, reason: reason.trim() }, key),
    onSuccess: () => {
      setReason("");
      void queryClient.invalidateQueries({ queryKey: ["customers"] }); // the list and its counts
      void queryClient.invalidateQueries({ queryKey: ["customer", id] }); // this drawer and its history
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  useEffect(() => {
    panel.current?.focus();
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [onClose]);

  const c = customer.data;
  return (
    <aside className="cust-drawer" ref={panel} tabIndex={-1} aria-label="KYC verification">
      <div className="cust-drawer__head">
        <h3>{c ? `KYC verification: ${c.name}` : "KYC verification"}</h3>
        <button type="button" className="cust-drawer__close" onClick={onClose} aria-label="Close">✕</button>
      </div>

      {customer.isPending && <div className="card skeleton" style={{ height: 200 }} aria-busy="true" />}
      {customer.isError && <div className="alert alert--danger">Could not load this customer. <button type="button" className="btn btn--sm" onClick={() => customer.refetch()}>Try again</button></div>}

      {c && (
        <>
          <div className="cust-tabs" role="tablist">
            <button type="button" role="tab" aria-selected={tab === "details"} className={tab === "details" ? "on" : ""} onClick={() => setTab("details")}>Details</button>
            <button type="button" role="tab" aria-selected={tab === "history"} className={tab === "history" ? "on" : ""} onClick={() => setTab("history")}>History</button>
          </div>

          {tab === "details" && (
            <>
              <div className="cust-kv"><span>Status</span><KycBadge status={c.kycStatus} /></div>
              <div className="cust-kv"><span>{c.idType}</span><span>{maskNin(c.idNumber)}</span></div>
              <div className="cust-kv"><span>Phone</span><span>{c.phone}</span></div>
              <div className="cust-kv"><span>Email</span><span>{c.email || "None given"}</span></div>
              <div className="cust-kv"><span>Address</span><span>{c.address}</span></div>
              <div className="cust-kv"><span>Submitted</span><span>{formatWAT(c.kycSubmittedAt)}</span></div>
              <div className="cust-kv"><span>Submitted by</span><span>{c.kycSubmittedBy}</span></div>
              <div className="cust-kv"><span>Linked SIMs</span><span>{c.linkedIccids.length ? c.linkedIccids.join(", ") : "None yet"}</span></div>
              <div className="cust-kv"><span>Blocked (separate from KYC)</span><span>{c.blocked ? "Yes" : "No"}</span></div>

              <div className="cust-preview">NIN submission preview<small>The submitted document will appear here once the backend provides it.</small></div>

              {c.kycStatus === "pending" ? (
                <>
                  <div className="field">
                    <label htmlFor="kyc-reason">Reason (required to reject)</label>
                    <textarea id="kyc-reason" className="input" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="For example: name does not match the NIN record" />
                  </div>
                  {decide.isError && <div className="alert alert--danger" style={{ marginBottom: 12 }}>{decide.error.message}</div>}
                  <div className="cust-actions">
                    <button type="button" className="btn btn--success" disabled={decide.isPending} onClick={() => decide.mutate("verified")}>Approve</button>
                    <button type="button" className="btn btn--danger" disabled={decide.isPending || reason.trim().length < 3} onClick={() => decide.mutate("rejected")}>Reject</button>
                  </div>
                  <p className="muted cust-note">Exact verification rules come from compliance (NCC SIM registration).</p>
                </>
              ) : (
                <div className="alert alert--warn">A KYC decision has already been recorded. See the History tab for who made it and why.</div>
              )}
            </>
          )}

          {tab === "history" && (
            <>
              {history.isPending && <p className="muted">Loading...</p>}
              {history.isError && <div className="alert alert--danger">Could not load the history.</div>}
              <ol className="cust-timeline">
                {history.data?.map((e) => (
                  <li key={`${e.at}-${e.action}`}>
                    <b>{e.action}</b> by {e.actor}
                    <small>{formatWAT(e.at)} &nbsp;|&nbsp; {e.reason}</small>
                  </li>
                ))}
              </ol>
            </>
          )}
        </>
      )}
    </aside>
  );
}
