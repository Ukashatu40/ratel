import { useEffect, useState, type FormEvent } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router";
import { formatClock } from "../../lib/format";
import { useCurrentUser } from "../../lib/useCurrentUser";
import { useAuth } from "../../lib/authContext";
import { Icon, type IconName } from "../ui";
import { initials } from "../../lib/format";
import "./layout.css";

const NAV: { to: string; label: string; icon: IconName }[] = [
  { to: "/", label: "Dashboard", icon: "dashboard" },
  { to: "/sales/activate", label: "Sell SIM", icon: "sim" },
  { to: "/lines", label: "Lines", icon: "lines" },
  { to: "/customers", label: "Customers", icon: "customers" },
  { to: "/plans", label: "Plans & Bundles", icon: "plans" },
  { to: "/inventory", label: "Stock & Vouchers", icon: "stock" },
  { to: "/finance/wallet", label: "Wallet", icon: "wallet" },
  { to: "/finance/reports", label: "Reports", icon: "reports" },
  { to: "/admin/audit", label: "Staff & Audit", icon: "staff" },
];

function Header() {
  const navigate = useNavigate();
  const user = useCurrentUser();
  const { signOut } = useAuth();
  const [query, setQuery] = useState("");
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);
  const search = (e: FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (q) navigate(`/lines?q=${encodeURIComponent(q)}`);
  };
  return (
    <header className="header">
      <Link to="/" className="header__logo"><img src="/ratel_logo.png" alt="Ratel: power to connect" /></Link>
      <form className="header__search" onSubmit={search}>
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search phone number, ICCID or IMSI" aria-label="Search lines" />
      </form>
      <span className="header__chip">WAT {formatClock(now)}</span>
      <button className="header__account" onClick={() => void signOut()} title="Sign out">
        <div className="header__avatar">{initials(user.name)}</div>
        <div className="header__user"><b>{user.name}</b><span>{user.role}</span></div>
      </button>
    </header>
  );
}

export function AppShell() {
  return (
    <div className="shell">
      <Header />
      <div className="shell__body">
        <nav className="sidebar" aria-label="Main">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) => `nav-link${isActive ? " nav-link--active" : ""}`}>
              <Icon name={n.icon} />{n.label}
            </NavLink>
          ))}
        </nav>
        <main className="shell__main"><Outlet /></main>
      </div>
    </div>
  );
}