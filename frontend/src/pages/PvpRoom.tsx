/**
 * A single PvP round.
 *
 * The screen is a pure renderer of backend state: the wheel, the countdown and
 * the winner all come from the server. Nothing here decides an outcome.
 */

import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import type { PvPPlayer } from "@shared/index";

import { BetInput } from "@/components/BetInput";
import { Avatar, Badge, Card, Screen, SectionTitle, Skeleton } from "@/components/ui";
import { api, newIdempotencyKey } from "@/lib/api";
import { gg, percent } from "@/lib/format";
import { useSession } from "@/lib/session";
import { haptics } from "@/lib/telegram";
import { useToast } from "@/lib/toast";
import { useCountdown, usePvpChannel } from "@/lib/usePvpChannel";

const PLAYER_COLORS = ["#55c8ff", "#6ff0ad", "#ffc93f", "#a98bff", "#ff6470", "#5ad1a4"];

export function PvpRoomPage() {
  const params = useParams<{ id: string }>();
  const gameId = Number(params.id);
  const toast = useToast();
  const { user, setBalance, refresh } = useSession();

  const { game, connected, transport, refresh: refreshChannel } = usePvpChannel(
    Number.isFinite(gameId) ? gameId : null,
  );
  const [bet, setBet] = useState(100);
  const [announced, setAnnounced] = useState(false);

  const secondsLeft = useCountdown(game?.status === "starting" ? game.spin_at : null);
  const joined = useMemo(
    () => game?.players.some((player) => player.user_id === user?.id) ?? false,
    [game, user],
  );

  const join = useMutation({
    mutationFn: () => api.pvpJoin(gameId, bet, newIdempotencyKey()),
    onSuccess: (result) => {
      haptics.tap("medium");
      setBalance(result.balance);
      void refreshChannel();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  // Announce the result once, when the round settles.
  useEffect(() => {
    if (!game || game.status !== "finished" || announced) return;
    setAnnounced(true);
    void refresh();
    if (game.winner_id === user?.id) {
      haptics.win();
      toast.success(`You won ${gg(game.prize)} GG`);
    } else if (joined) {
      haptics.lose();
      toast.show("Not this time — the pot went elsewhere");
    }
  }, [game, announced, joined, user?.id, refresh, toast]);

  if (!game) {
    return (
      <Screen>
        <Skeleton height={120} count={2} />
      </Screen>
    );
  }

  const winner = game.players.find((player) => player.user_id === game.winner_id);

  return (
    <Screen>
      <div className="row-between">
        <div className="row" style={{ gap: "var(--sp-2)" }}>
          <h1>Round #{game.id}</h1>
          <Badge status={game.status} />
        </div>
        <span className="faint">{connected ? transport : "reconnecting…"}</span>
      </div>

      <div className="stage stack">
        <div className="row-between">
          <span className="faint">Total pot</span>
          <strong className="num" style={{ fontSize: 26, color: "var(--accent)" }}>
            {gg(game.total_pool)} GG
          </strong>
        </div>

        <div className="pointer" />
        <Wheel players={game.players} />

        {game.status === "starting" ? (
          <div className="countdown">{secondsLeft}s</div>
        ) : game.status === "spinning" ? (
          <div className="countdown" style={{ color: "var(--accent)" }}>
            drawing…
          </div>
        ) : game.status === "finished" && winner ? (
          <div className="result" data-outcome={winner.user_id === user?.id ? "win" : "lose"}>
            <Avatar src={winner.avatar} name={winner.name} size="lg" />
            <strong>{winner.name}</strong>
            <span className="amount num">{gg(game.prize)} GG</span>
            <span className="faint">
              won with {percent(winner.chance)} · roll {game.winning_roll?.toFixed(6)}
            </span>
          </div>
        ) : (
          <p className="faint" style={{ textAlign: "center" }}>
            Waiting for a second player…
          </p>
        )}
      </div>

      {game.status === "waiting" || game.status === "starting" ? (
        <Card>
          <BetInput
            value={bet}
            onChange={setBet}
            min={game.min_bet}
            max={1_000_000}
            balance={user?.balance ?? 0}
            disabled={join.isPending}
          />
          <button
            className="btn btn-primary btn-block"
            style={{ marginTop: "var(--sp-3)" }}
            disabled={join.isPending || bet > (user?.balance ?? 0)}
            onClick={() => join.mutate()}
          >
            {join.isPending ? "Joining…" : joined ? `Add ${gg(bet)} GG` : `Join with ${gg(bet)} GG`}
          </button>
        </Card>
      ) : null}

      <SectionTitle>Players</SectionTitle>
      <div className="stack">
        {game.players.map((player, index) => (
          <div key={player.user_id} className="card card-tight row-between">
            <div className="row">
              <span
                style={{
                  width: 4,
                  height: 32,
                  borderRadius: 4,
                  background: PLAYER_COLORS[index % PLAYER_COLORS.length],
                }}
              />
              <Avatar src={player.avatar} name={player.name} />
              <div className="stack" style={{ gap: 0 }}>
                <strong style={{ fontSize: 14 }}>
                  {player.name}
                  {player.user_id === user?.id ? " · you" : ""}
                </strong>
                <span className="faint num">{gg(player.amount)} GG</span>
              </div>
            </div>
            <strong className="num" style={{ color: player.is_winner ? "var(--win)" : undefined }}>
              {percent(player.chance)}
            </strong>
          </div>
        ))}
      </div>

      <Card tight>
        <span className="section-title">Provably fair</span>
        <p className="faint" style={{ wordBreak: "break-all", marginTop: 6 }}>
          seed hash: {game.server_seed_hash}
          <br />
          client seed: {game.client_seed} · nonce {game.nonce}
          {game.server_seed ? (
            <>
              <br />
              revealed seed: {game.server_seed}
            </>
          ) : null}
        </p>
      </Card>
    </Screen>
  );
}

function Wheel({ players }: { players: PvPPlayer[] }) {
  const total = players.reduce((sum, player) => sum + player.amount, 0) || 1;
  return (
    <div className="wheel">
      {players.map((player, index) => (
        <span
          key={player.user_id}
          style={{
            width: `${(player.amount / total) * 100}%`,
            background: PLAYER_COLORS[index % PLAYER_COLORS.length],
          }}
        />
      ))}
    </div>
  );
}
