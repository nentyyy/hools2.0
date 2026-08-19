import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "@/components/Layout";
import { TopUpSheet } from "@/components/TopUpSheet";
import { Screen } from "@/components/ui";
import { useSession } from "@/lib/session";
import { GiveawaysPage } from "@/pages/Giveaways";
import { HomePage } from "@/pages/Home";
import { ProfilePage } from "@/pages/Profile";
import { PvpRoomPage } from "@/pages/PvpRoom";
import { SoloPage } from "@/pages/Solo";
import { HiLoPage } from "@/pages/solo/HiLo";
import { IceArenaPage } from "@/pages/solo/IceArena";
import { LuckyBuyPage } from "@/pages/solo/LuckyBuy";
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
    return (
      <div className="app">
        <Screen>
          <div className="empty">
            <span className="glyph">🔒</span>
            <strong>Can't sign you in</strong>
            <span className="faint">{error}</span>
            <button className="btn btn-primary" style={{ marginTop: "var(--sp-4)" }} onClick={retry}>
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
          <Route path="/" element={<HomePage />} />
          <Route path="/pvp" element={<Navigate to="/" replace />} />
          <Route path="/pvp/:id" element={<PvpRoomPage />} />
          <Route path="/solo" element={<SoloPage />} />
          <Route path="/solo/plinko" element={<PlinkoPage />} />
          <Route path="/solo/upgrade" element={<UpgradePage />} />
          <Route path="/solo/lucky-buy" element={<LuckyBuyPage />} />
          <Route path="/solo/hi-lo" element={<HiLoPage />} />
          <Route path="/solo/ice-arena" element={<IceArenaPage />} />
          <Route path="/giveaways" element={<GiveawaysPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
      <TopUpSheet open={topUp} onClose={() => setTopUp(false)} />
    </>
  );
}
