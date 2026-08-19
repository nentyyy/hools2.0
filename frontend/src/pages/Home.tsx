/** PvP arena: live lobbies, plus the entry point for creating one. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import type { PvPGame } from "@shared/index";
import { SOLO_MODES } from "@shared/index";

import { BetInput } from "@/components/BetInput";
import { Avatar, Badge, Card, Empty, Screen, SectionTitle, Sheet, Skeleton } from "@/components/ui";
import { api, newIdempotencyKey } from "@/lib/api";
import { gg, percent } from "@/lib/format";
import { useSession } from "@/lib/session";
import { haptics } from "@/lib/telegram";
import { useToast } from "@/lib/toast";

export function HomePage() {
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { user, setBalance } = useSession();

  const [creating, setCreating] = useState(false);
  const [bet, setBet] = useState(100);

  const { data, isLoading } = useQuery({
    queryKey: ["pvp", "list"],
    queryFn: () => api.pvpList({ limit: 20 }),
    refetchInterval: 4000,
  });

  const createGame = useMutation({
    mutationFn: () => api.pvpCreate(bet, newIdempotencyKey()),
    onSuccess: (result) => {
      haptics.win();
      setBalance(result.balance);
      setCreating(false);
      void queryClient.invalidateQueries({ queryKey: ["pvp", "list"] });
      navigate(`/pvp/${result.game.id}`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const config = data?.config;
  const games = data?.items ?? [];

  return (
    <Screen>
      <div className="stack" style={{ gap: "var(--sp-1)" }}>
        <h1>PvP arena</h1>
        <p className="muted" style={{ fontSize: 14 }}>
          Everyone throws GG into one pot. Your share of the pot is your chance to take it all —
          the winner is drawn on the server from a seed you can verify afterwards.
        </p>
      </div>

      <button className="btn btn-primary btn-block" onClick={() => { haptics.tap("medium"); setCreating(true); }}>
        Create a round
      </button>

      <SectionTitle action={<span className="faint">{games.length} live</span>}>Open rounds</SectionTitle>

      {isLoading ? (
        <Skeleton height={92} />
      ) : games.length === 0 ? (
        <Empty glyph="⚔️" title="No open rounds" hint="Create one and wait for a challenger." />
      ) : (
        <div className="stack">
          {games.map((game) => (
            <LobbyCard key={game.id} game={game} onOpen={() => navigate(`/pvp/${game.id}`)} />
          ))}
        </div>
      )}

      <SectionTitle action={<button className="chip" onClick={() => navigate("/solo")}>All</button>}>
        Solo modes
      </SectionTitle>
      <div className="grid-2">
        {SOLO_MODES.slice(0, 4).map((mode) => (
          <Card key={mode.slug} onClick={() => navigate(`/solo/${mode.slug}`)} tight>
            <strong>{mode.title}</strong>
            <p className="faint">{mode.blurb}</p>
          </Card>
        ))}
      </div>

      <Sheet open={creating} onClose={() => setCreating(false)} title="Create a PvP round">
        <BetInput
          value={bet}
          onChange={setBet}
          min={config?.min_bet ?? 10}
          max={config?.max_bet ?? 100000}
          balance={user?.balance ?? 0}
          disabled={createGame.isPending}
        />
        <p className="faint" style={{ margin: "var(--sp-3) 0" }}>
          The round starts {config?.countdown_seconds ?? 20}s after a second player joins.
          House fee: {config?.rake_percent ?? 5}% of the pot.
        </p>
        <button
          className="btn btn-primary btn-block"
          disabled={createGame.isPending || bet > (user?.balance ?? 0)}
          onClick={() => createGame.mutate()}
        >
          {createGame.isPending ? "Creating…" : `Stake ${gg(bet)} GG`}
        </button>
      </Sheet>
    </Screen>
  );
}

function LobbyCard({ game, onOpen }: { game: PvPGame; onOpen: () => void }) {
  return (
    <Card onClick={onOpen}>
      <div className="row-between" style={{ marginBottom: "var(--sp-3)" }}>
        <div className="row" style={{ gap: "var(--sp-2)" }}>
          <Badge status={game.status} />
          <span className="faint">#{game.id}</span>
        </div>
        <strong className="num" style={{ color: "var(--accent)" }}>
          {gg(game.total_pool)} GG
        </strong>
      </div>

      <div className="row-between">
        <div className="row" style={{ gap: -8 }}>
          {game.players.slice(0, 4).map((player) => (
            <span key={player.user_id} style={{ marginLeft: -8 }}>
              <Avatar src={player.avatar} name={player.name} />
            </span>
          ))}
          {game.players.length > 4 ? <span className="faint">+{game.players.length - 4}</span> : null}
        </div>
        <span className="faint num">
          {game.players.length}/{game.max_players} · top {percent(Math.max(...game.players.map((p) => p.chance), 0), 0)}
        </span>
      </div>
    </Card>
  );
}
