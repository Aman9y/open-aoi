import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../api";
import type { Reference } from "../types";

const NAV = [
  { to: "/inspect", label: "Inspect", ico: "⊙" },
  { to: "/history", label: "History", ico: "≣" },
  { to: "/analytics", label: "Analytics", ico: "▤" },
  { to: "/references", label: "References", ico: "◫" },
];

export function Layout() {
  const [online, setOnline] = useState<boolean | null>(null);
  const [yolo, setYolo] = useState("");
  const [active, setActive] = useState<Reference | null>(null);
  const loc = useLocation();
  const pageName = NAV.find((n) => loc.pathname.startsWith(n.to))?.label ?? "";

  useEffect(() => {
    let alive = true;
    const ping = () => {
      api.health()
        .then((h) => alive && (setOnline(true), setYolo(h.yolo)))
        .catch(() => alive && setOnline(false));
      api.activeReference().then((r) => alive && setActive(r)).catch(() => {});
    };
    ping();
    const t = setInterval(ping, 8000);
    return () => { alive = false; clearInterval(t); };
  }, [loc.pathname]);

  return (
    <div className="app">
      <div className="brandbox">
        <span className="logo" />
        AI&nbsp;QUALITY&nbsp;INSPECTION
      </div>

      <header className="topbar">
        <span className="page-name">{pageName}</span>
        <div className="meta">
          {active && (
            <span>
              Reference <b>{active.id}</b>{" "}
              <span className={"pill " + active.kind}>{active.kind}</span>
            </span>
          )}
          <span>
            Model <b>{yolo === "READY" ? "YOLO" : "OFF"}</b>
          </span>
          <span className="row" style={{ gap: 7 }}>
            <span className={"dot" + (online ? "" : " off")} />
            {online == null ? "connecting…" : online ? "SYSTEM READY" : "BACKEND OFFLINE"}
          </span>
        </div>
      </header>

      <nav className="sidebar">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to}>
            <span className="ico">{n.ico}</span>
            {n.label}
          </NavLink>
        ))}
      </nav>

      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
