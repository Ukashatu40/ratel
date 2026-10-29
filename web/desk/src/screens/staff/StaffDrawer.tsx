import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { newIdempotencyKey } from "../../lib/api";
import { createStaff, updateStaff } from "./api";
import { ROLES, type Role, type StaffMember } from "./types";

// Create (member === null) or edit a staff account. Email and name are fixed once the account exists.
export function StaffDrawer({ member, isSelf, onClose }: { member: StaffMember | null; isSelf: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const panel = useRef<HTMLElement>(null);
  const [name, setName] = useState(member?.name ?? "");
  const [email, setEmail] = useState(member?.email ?? "");
  const [role, setRole] = useState<Role>(member?.role ?? "Customer Care");
  const [vpn, setVpn] = useState(member?.vpnAccess ?? true);
  const [active, setActive] = useState(member?.active ?? true);
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [key] = useState(newIdempotencyKey); // one key per save, so a retry cannot create or change twice

  const save = useMutation({
    mutationFn: () => (member ? updateStaff(member.id, { role, vpnAccess: vpn, active, reason: reason.trim() }, key) : createStaff({ name: name.trim(), email: email.trim(), role, vpnAccess: vpn }, key)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["staff"] });
      void queryClient.invalidateQueries({ queryKey: ["audit"] });
      onClose();
    },
  });

  useEffect(() => {
    panel.current?.focus();
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [onClose]);

  const needsReason = !!member && (role !== member.role || active !== member.active);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const found: Record<string, string> = {};
    if (!member) {
      if (!name.trim()) found.name = "Enter the staff member's full name";
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) found.email = "Enter a valid email address";
    }
    if (needsReason && reason.trim().length < 3) found.reason = "A reason is required to change a role or disable an account";
    setErrors(found);
    if (Object.keys(found).length === 0) save.mutate();
  };

  return (
    <aside className="stf-drawer" ref={panel} tabIndex={-1} aria-label="Staff account">
      <div className="stf-drawer__head">
        <h3>{member ? `Edit ${member.name}` : "Add a staff member"}</h3>
        <button type="button" className="stf-drawer__close" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <form onSubmit={submit} noValidate>
        <div className="field"><label htmlFor="s-name">Full name</label><input id="s-name" className="input" value={name} disabled={!!member} onChange={(e) => setName(e.target.value)} />{errors.name && <span className="field__error">{errors.name}</span>}</div>
        <div className="field"><label htmlFor="s-email">Email (the sign-in name)</label><input id="s-email" className="input" type="email" value={email} disabled={!!member} onChange={(e) => setEmail(e.target.value)} />{errors.email && <span className="field__error">{errors.email}</span>}</div>
        <div className="field">
          <label htmlFor="s-role">Role</label>
          <select id="s-role" className="input" value={role} disabled={isSelf} onChange={(e) => setRole(e.target.value as Role)}>{ROLES.map((r) => <option key={r} value={r}>{r}</option>)}</select>
        </div>
        <label className="stf-check"><input type="checkbox" checked={vpn} onChange={(e) => setVpn(e.target.checked)} /> VPN access (can use RatelDesk away from the office)</label>
        {member && (
          <div className="field">
            <label htmlFor="s-status">Account</label>
            <select id="s-status" className="input" value={active ? "active" : "disabled"} disabled={isSelf} onChange={(e) => setActive(e.target.value === "active")}>
              <option value="active">Active</option><option value="disabled">Disabled (cannot sign in)</option>
            </select>
          </div>
        )}
        {isSelf && <div className="alert alert--warn" style={{ marginBottom: 14 }}>You cannot change your own role or disable your own account.</div>}
        {needsReason && (
          <div className="field">
            <label htmlFor="s-reason">Reason (required, saved in the audit log)</label>
            <textarea id="s-reason" className="input" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
            {errors.reason && <span className="field__error">{errors.reason}</span>}
          </div>
        )}
        {save.isError && <div className="alert alert--danger" style={{ marginBottom: 12 }}>{save.error.message}</div>}
        <div className="stf-actions">
          <button type="button" className="btn btn--outline" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn" disabled={save.isPending}>{save.isPending ? "Saving..." : member ? "Save changes" : "Add staff member"}</button>
        </div>
        {!member && <p className="muted stf-note">How a new member gets their first password depends on the sign-in method, which is still to be decided.</p>}
      </form>
    </aside>
  );
}
