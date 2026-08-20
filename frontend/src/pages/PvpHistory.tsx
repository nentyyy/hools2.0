/** Recent finished rounds, newest first. */

import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { Avatar, Empty, Screen, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { gg, percent, relative } from "@/lib/format";

export function PvpHistoryPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["pvp", "history"],
    queryFn: () => api.pvpList({ status: "finished", limit: 30 }),
  });

  return (
    <Screen>
      <h1>Round history</h1>

      {isLoading ? (
        <Skeleton height={64} count={5} />
      ) : !data?.items.length ? (
        <Empty glyph="↺" title="No finished rounds yet" />
      ) : (
        <div className="stack" style={{ gap: "var(--sp-2)" }}>
          {data.items.map((game) => {
            const winner = game.players.find((player) => player.user_id === game.winner_id);
            return (
              <button
                key={game.id}
                className="player-row"
                style={{ width: "100%", textAlign: "left" }}
                onClick={() => navigate(`/pvp/${game.id}`)}
              >
                <Avatar src={winner?.avatar} name={winner?.name ?? "—"} />
                <div className="stack" style={{ gap: 0, flex: 1, minWidth: 0 }}>
                  <strong style={{ fontSize: 14 }}>{winner?.name ?? "cancelled"}</strong>
                  <span className="faint num">
                    #{game.id} · {game.players.length} players · {relative(game.finished_at ?? game.created_at)}
                  </span>
                </div>
                <div className="stack" style={{ gap: 0, alignItems: "flex-end" }}>
                  <strong className="num" style={{ color: "var(--win)" }}>
                    +{gg(game.prize)}
                  </strong>
                  <span className="faint num">
                    {winner ? percent(winner.chance, 0) : "—"}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </Screen>
  );
}
