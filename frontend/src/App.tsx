import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "@/components/Layout";
import { TopUpSheet } from "@/components/TopUpSheet";
import { Screen } from "@/components/ui";
import { useSession } from "@/lib/session";
import { ArenaPage } from "@/pages/Arena";
import { GiveawaysPage } from "@/pages/Giveaways";
import { ProfilePage } from "@/pages/Profile";
import { PvpHistoryPage } from "@/pages/PvpHistory";
import { PvpReplayPage } from "@/pages/PvpReplay";
import { SoloPage } from "@/pages/Solo";
import { AdminPage } from "@/pages/Admin";
import { LuckyBuyPage } from "@/pages/LuckyBuy";
import { ShopPage } from "@/pages/Shop";
import { HiLoPage } from "@/pages/solo/HiLo";
import { IceArenaPage } from "@/pages/solo/IceArena";
import { PlinkoPage } from "@/pages/solo/Plinko";
import { UpgradePage } from "@/pages/solo/Upgrade";

export default function App() {
  const { status, error, retry } = useSession();
  const [topUp, setTopUp] = useState(false);

  if (status === "loading") {
    return (
      <div className="app">
        <Screen>
          <div className="skeleton" style={{ height: 72 }} />
          <div className="skeleton" style={{ height: 180 }} />
          <div className="skeleton" style={{ height: 120 }} />
        </Screen>
      </div>
    );
  }

  if (status === "error") {
    const botUrl = `https://t.me/${import.meta.env.VITE_BOT_USERNAME ?? ""}`;
    return (
      <div className="app">
        <Screen>
          <div className="empty">
            <span className="glyph">🔒</span>
            <strong>Can't sign you in</strong>
            <span className="faint">{error}</span>
            {import.meta.env.VITE_BOT_USERNAME ? (
              <a className="btn btn-primary" style={{ marginTop: "var(--sp-4)" }} href={botUrl}>
                Open in Telegram
              </a>
            ) : null}
            <button className="btn btn-ghost btn-sm" style={{ marginTop: "var(--sp-2)" }} onClick={retry}>
              Try again
            </button>
          </div>
        </Screen>
      </div>
    );
  }

  return (
    <>
      <Routes>
        <Route element={<Layout onTopUp={() => setTopUp(true)} />}>
          <Route path="/" element={<ArenaPage />} />
          <Route path="/pvp" element={<Navigate to="/" replace />} />
          <Route path="/pvp/history" element={<PvpHistoryPage />} />
          <Route path="/pvp/:id" element={<PvpReplayPage />} />
          <Route path="/solo" element={<SoloPage />} />
          <Route path="/solo/plinko" element={<PlinkoPage />} />
          <Route path="/solo/upgrade" element={<UpgradePage />} />
          <Route path="/shop" element={<ShopPage />} />
          <Route path="/shop/:code" element={<LuckyBuyPage />} />
          <Route path="/solo/hi-lo" element={<HiLoPage />} />
          <Route path="/solo/ice-arena" element={<IceArenaPage />} />
          <Route path="/giveaways" element={<GiveawaysPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
      <TopUpSheet open={topUp} onClose={() => setTopUp(false)} />
    </>
  );
}
