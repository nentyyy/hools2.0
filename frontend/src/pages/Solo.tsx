/** Solo hub: every mode, plus any run that is still open. */

import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { SOLO_MODES } from "@shared/index";

import { Card, Empty, Screen, SectionTitle, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { gg, multiplier, relative } from "@/lib/format";
import { haptics } from "@/lib/telegram";

const ICONS: Record<string, string> = {
  plinko: "🟣",
  upgrade: "🔺",
  "lucky-buy": "🎁",
  "hi-lo": "🃏",
  "ice-arena": "🧊",
};

export function SoloPage() {
  const navigate = useNavigate();

  const { data: active } = useQuery({ queryKey: ["solo", "active"], queryFn: api.soloActive });
  const { data: history, isLoading } = useQuery({
    queryKey: ["solo", "history"],
    queryFn: () => api.soloHistory({ limit: 12 }),
  });

  const resumable = [
    active?.hi_lo ? { slug: "hi-lo", label: "Hi-Lo", state: active.hi_lo } : null,
    active?.ice_arena ? { slug: "ice-arena", label: "Ice Arena", state: active.ice_arena } : null,
  ].filter(Boolean) as { slug: string; label: string; state: { potential_reward: number; round: number } }[];

  return (
    <Screen>
      <h1>Solo modes</h1>

      {resumable.length > 0 ? (
        <>
          <SectionTitle>Continue</SectionTitle>
          {resumable.map((item) => (
            <Card key={item.slug} onClick={() => navigate(`/solo/${item.slug}`)}>
              <div className="row-between">
                <div className="stack" style={{ gap: 0 }}>
                  <strong>{item.label}</strong>
                  <span className="faint">round {item.state.round} in progress</span>
                </div>
                <strong className="num" style={{ color: "var(--win)" }}>
                  {gg(item.state.potential_reward)} GG
                </strong>
              </div>
            </Card>
          ))}
        </>
      ) : null}

      <div className="stack">
        {SOLO_MODES.map((mode) => (
          <Card
            key={mode.slug}
            onClick={() => {
              haptics.tap();
              navigate(`/solo/${mode.slug}`);
            }}
          >
            <div className="row">
              <span style={{ fontSize: 26 }}>{ICONS[mode.slug]}</span>
              <div className="stack" style={{ gap: 0 }}>
                <strong>{mode.title}</strong>
                <span className="faint">{mode.blurb}</span>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <SectionTitle>Recent rounds</SectionTitle>
      {isLoading ? (
        <Skeleton height={48} count={3} />
      ) : !history?.items.length ? (
        <Empty glyph="🎲" title="No rounds yet" hint="Pick a mode above to start." />
      ) : (
        <Card>
          {history.items.map((game) => (
            <div key={game.id} className="list-item">
              <div className="stack" style={{ gap: 0, flex: 1 }}>
                <strong style={{ fontSize: 14 }}>{game.game_type.replace(/_/g, " ")}</strong>
                <span className="faint">{relative(game.created_at)}</span>
              </div>
              <span className="faint num">{multiplier(game.multiplier)}</span>
              <strong className={game.reward > 0 ? "amount-pos num" : "amount-neg num"}>
                {game.reward > 0 ? `+${gg(game.reward)}` : `−${gg(game.bet)}`}
              </strong>
            </div>
          ))}
        </Card>
      )}
    </Screen>
  );
}
