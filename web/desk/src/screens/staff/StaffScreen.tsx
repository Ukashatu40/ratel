import { useSearchParams } from "react-router";
import { AuditTab } from "./AuditTab";
import { StaffTab } from "./StaffTab";
import "./StaffScreen.css";

export default function StaffScreen() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "audit" ? "audit" : "staff"; // the open tab lives in the URL
  return (
    <div className="stf">
      <div>
        <h1>Staff &amp; Audit</h1>
        <p className="muted" style={{ marginTop: 4 }}>Who can use RatelDesk, and everything they have done.</p>
      </div>
      <div className="stf-tabs" role="tablist">
        <button type="button" role="tab" aria-selected={tab === "staff"} className={tab === "staff" ? "on" : ""} onClick={() => setParams({}, { replace: true })}>Staff accounts</button>
        <button type="button" role="tab" aria-selected={tab === "audit"} className={tab === "audit" ? "on" : ""} onClick={() => setParams({ tab: "audit" }, { replace: true })}>Audit log</button>
      </div>
      {tab === "staff" ? <StaffTab /> : <AuditTab />}
    </div>
  );
}
