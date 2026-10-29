import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "../../components/ui";
import { formatWAT, initials } from "../../lib/format";
import { useCurrentUser } from "../../lib/useCurrentUser";
import { getStaff } from "./api";
import { StaffDrawer } from "./StaffDrawer";
import type { StaffMember } from "./types";

export function StaffTab() {
  const me = useCurrentUser();
  const canManage = me.role === "Super Admin"; // the backend must enforce this too
  const { data, isPending, isError, refetch } = useQuery({ queryKey: ["staff"], queryFn: getStaff });
  const [open, setOpen] = useState<{ member: StaffMember | null } | null>(null);
  return (
    <div className="stf-col">
      <div className="stf-bar">
        {canManage ? <button type="button" className="btn" onClick={() => setOpen({ member: null })}>Add staff member</button> : <div className="alert alert--warn">Only a Super Admin can add or change staff accounts. You can see who has access.</div>}
      </div>
      <section className={`card stf-card${open ? " stf-card--open" : ""}`}>
        {isError ? <div className="stf-message">Could not load staff. <button type="button" className="btn btn--sm" onClick={() => refetch()}>Try again</button></div> : (
          <table className="data-table">
            <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>VPN</th><th>Account</th><th>Last sign-in (WAT)</th>{canManage && <th>Actions</th>}</tr></thead>
            <tbody>
              {isPending && <tr><td colSpan={7} className="muted">Loading...</td></tr>}
              {data?.map((s) => (
                <tr key={s.id}>
                  <td><div className="stf-name"><span className="avatar">{initials(s.name)}</span>{s.name}{s.email === me.email && <Badge tone="blue">You</Badge>}</div></td>
                  <td>{s.email}</td>
                  <td>{s.role === "Super Admin" ? <Badge tone="amber">Super Admin</Badge> : <Badge tone="blue">Customer Care</Badge>}</td>
                  <td>{s.vpnAccess ? <Badge tone="green">VPN</Badge> : <Badge tone="grey">Office only</Badge>}</td>
                  <td>{s.active ? <Badge tone="green">Active</Badge> : <Badge tone="grey">Disabled</Badge>}</td>
                  <td>{s.lastSignInAt ? formatWAT(s.lastSignInAt) : <span className="muted">Never</span>}</td>
                  {canManage && <td><button type="button" className="btn btn--outline btn--sm" onClick={() => setOpen({ member: s })}>Edit</button></td>}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {open && <StaffDrawer key={open.member?.id ?? "new"} member={open.member} isSelf={!!open.member && open.member.email === me.email} onClose={() => setOpen(null)} />}
    </div>
  );
}
