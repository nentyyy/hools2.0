/** App shell: balance header, routed content and the bottom tab bar. */

import { useEffect } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";

import { gg } from "@/lib/format";
import { useSession } from "@/lib/session";
import { backButton, haptics } from "@/lib/telegram";

import { Avatar } from "./ui";

const TABS = [
  { path: "/", icon: "⚔️", label: "PvP" },
  { path: "/solo", icon: "🎲", label: "Solo" },
  { path: "/giveaways", icon: "🎁", label: "Drops" },
  { path: "/profile", icon: "👤", label: "Profile" },
];

export function Layout({ onTopUp }: { onTopUp: () => void }) {
  const { user } = useSession();
  const location = useLocation();
  const navigate = useNavigate();

  const isRoot = TABS.some((tab) => tab.path === location.pathname);

  // Telegram's own back button drives navigation on inner screens.
  useEffect(() => {
    if (isRoot) return;
    return backButton.show(() => navigate(-1));
  }, [isRoot, location.pathname, navigate]);

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/profile" className="row" style={{ gap: "var(--sp-2)", color: "inherit" }}>
          <Avatar src={user?.avatar} name={user?.first_name ?? "Player"} />
          <div className="stack" style={{ gap: 0 }}>
            <strong style={{ fontSize: 14 }}>{user?.first_name ?? "Player"}</strong>
            <span className="faint">Level {user?.level ?? 1}</span>
          </div>
        </Link>

        <button className="balance-pill num" onClick={() => { haptics.tap(); onTopUp(); }}>
          {gg(user?.balance ?? 0)} GG
          <span className="plus">+</span>
        </button>
      </header>

      <Outlet />

      <nav className="tabbar">
        {TABS.map((tab) => (
          <Link
            key={tab.path}
            to={tab.path}
            data-active={location.pathname === tab.path}
            onClick={() => haptics.select()}
          >
            <span className="tab-icon">{tab.icon}</span>
            {tab.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
