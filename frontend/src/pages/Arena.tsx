/**
 * PvP arena — the app's main screen.
 *
 * One round is running at a time: everyone who joins lands in the same pot.
 * The screen only renders what the backend committed — the pot, the shares, the
 * countdown and the drawn ticket. Pressing the button sends a bet and nothing
 * else; the wheel is told where to stop, it never decides.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { PvPGame } from "@shared/index";

import { HistoryIcon, UsersIcon } from "@/components/icons";
import { IceRink } from "@/components/IceRink";
import { PLAYER_COLORS, Wheel } from "@/components/Wheel";
import { Avatar, Screen } from "@/components/ui";
import { api, newIdempotencyKey, type PvPHighlightEntry } from "@/lib/api";
import { gg, percent } from "@/lib/format";
import { useSession } from "@/lib/session";
import { haptics } from "@/lib/telegram";
import { useToast } from "@/lib/toast";
import { useCountdown, usePvpChannel } from "@/lib/usePvpChannel";

const BET_PRESETS = [10, 50, 100, 500, 1000];

export function ArenaPage() {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user, setBalance, refresh } = useSession();

  const [bet, setBet] = useState(100);
  const [announced, setAnnounced] = useState<number | null>(null);
  // Two ways to watch the same round; the choice is remembered per device.
  const [view, setView] = useState<"wheel" | "ice">(
    () => (localStorage.getItem("gg.arena-view") as "wheel" | "ice") ?? "wheel",
  );

  const current = useQuery({
    queryKey: ["pvp", "current"],
    queryFn: api.pvpCurrent,
    // The draw is published when the spin starts, so the closer a round is to
    // resolving the more it matters that we hear about it promptly.
    refetchInterval: (query) => {
      const status = query.state.data?.game?.status;
      return status === "starting" || status === "spinning" ? 1000 : 3000;
    },
  });
  const highlights = useQuery({
    queryKey: ["pvp", "highlights"],
    queryFn: api.pvpHighlights,
    refetchInterval: 15000,
  });

  const gameId = current.data?.game?.id ?? null;
  const channel = usePvpChannel(gameId);
  // The websocket snapshot is fresher than the poll; fall back to the poll.
  const game: PvPGame | null = channel.game ?? current.data?.game ?? null;
  const config = current.data?.config;

  const secondsLeft = useCountdown(game?.status === "starting" ? game.spin_at : null);
  const joined = useMemo(
    () => game?.players.some((player) => player.user_id === user?.id) ?? false,
    [game, user?.id],
  );

  const join = useMutation({
    mutationFn: () => api.pvpQuickJoin(bet, newIdempotencyKey()),
    onSuccess: (result) => {
      haptics.tap("medium");
      setBalance(result.balance);
      void queryClient.invalidateQueries({ queryKey: ["pvp"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  // Announce a result once per round.
  useEffect(() => {
    if (!game || game.status !== "finished" || announced === game.id) return;
    setAnnounced(game.id);
    void refresh();
    void queryClient.invalidateQueries({ queryKey: ["pvp", "highlights"] });

    if (!joined) return;
    if (game.winner_id === user?.id) {
      haptics.win();
      toast.success(`You won ${gg(game.prize)} GG`);
    } else {
      haptics.lose();
    }
  }, [game, announced, joined, user?.id, refresh, queryClient, toast]);

  const winner = game?.players.find((player) => player.user_id === game.winner_id) ?? null;
  const status = <ArenaStatus game={game} winner={winner} secondsLeft={secondsLeft} />;
  const spinning = game?.status === "spinning";
  const settled = game === null || game.status === "finished" || game.status === "cancelled";
  const affordable = bet <= (user?.balance ?? 0);

  return (
    <Screen>
      <div className="ticker">
        <TickerCard label="Last" entry={highlights.data?.last ?? null} />
        <TickerCard label="Top" entry={highlights.data?.top ?? null} tone="gold" />
      </div>

      <div className="pool-bar">
        <button className="icon-btn" onClick={() => navigate("/pvp/history")} aria-label="Round history">
          <HistoryIcon size={19} />
        </button>
        <div className="pool-total num">
          <span className="label">Pot</span>
          <span style={{ color: "var(--accent)" }}>{gg(game?.total_pool ?? 0)} GG</span>
        </div>
        <div className="icon-btn online-pill" title="Players online">
          <UsersIcon size={15} />
          <span className="num">{highlights.data?.online ?? "—"}</span>
        </div>
      </div>

      <div className="view-switch">
        {(["wheel", "ice"] as const).map((value) => (
          <button
            key={value}
            data-active={view === value}
            onClick={() => {
              haptics.select();
              setView(value);
              localStorage.setItem("gg.arena-view", value);
            }}
          >
            {value === "wheel" ? "Wheel" : "Ice arena"}
          </button>
        ))}
      </div>

      {view === "wheel" ? (
        <Wheel
          players={game?.players ?? []}
          totalPool={game?.total_pool ?? 0}
          winningRoll={game?.status === "finished" || spinning ? game?.winning_roll ?? null : null}
          spinAt={game?.spin_at ?? null}
          spinSeconds={game?.spin_seconds ?? 6}
          spinning={spinning}
        >
          {status}
        </Wheel>
      ) : (
        <IceRink
          players={game?.players ?? []}
          totalPool={game?.total_pool ?? 0}
          winningRoll={game?.status === "finished" || spinning ? game?.winning_roll ?? null : null}
          spinAt={game?.spin_at ?? null}
          spinSeconds={game?.spin_seconds ?? 6}
        >
          {status}
        </IceRink>
      )}

      {game?.status === "finished" && winner ? (
        <div className="winner-banner">
          <Avatar src={winner.avatar} name={winner.name} />
          <div className="stack" style={{ gap: 0, flex: 1 }}>
            <strong>{winner.user_id === user?.id ? "You won" : `${winner.name} won`}</strong>
            <span className="faint num">
              {gg(game.total_pool)} pot · {percent(winner.chance)} chance
            </span>
          </div>
          <strong className="num" style={{ color: "var(--win)" }}>
            +{gg(game.prize)}
          </strong>
        </div>
      ) : null}

      <div className="bet-bar">
        {BET_PRESETS.filter((preset) => preset >= (config?.min_bet ?? 10)).map((preset) => (
          <button
            key={preset}
            className="bet-chip"
            data-active={bet === preset}
            onClick={() => {
              haptics.select();
              setBet(preset);
            }}
          >
            {gg(preset)}
          </button>
        ))}
        <button
          className="bet-chip"
          data-active={bet === (user?.balance ?? 0) && (user?.balance ?? 0) > 0}
          onClick={() => {
            haptics.select();
            setBet(Math.max(config?.min_bet ?? 10, Math.min(user?.balance ?? 0, config?.max_bet ?? 100000)));
          }}
        >
          Max
        </button>
      </div>

      <button
        className="btn btn-primary btn-block"
        disabled={join.isPending || !affordable}
        onClick={() => join.mutate()}
      >
        {join.isPending
          ? "Joining…"
          : !affordable
            ? "Not enough GG"
            : settled
              ? `Start a round with ${gg(bet)} GG`
              : joined
                ? `Add ${gg(bet)} GG`
                : `Join with ${gg(bet)} GG`}
      </button>

      <div className="row-between">
        <span className="section-title">
          {game?.players.length ?? 0} {game?.players.length === 1 ? "player" : "players"}
        </span>
        <span className="faint num">{game ? `Round #${game.id}` : "—"}</span>
      </div>

      <div className="stack" style={{ gap: "var(--sp-2)" }}>
        {(game?.players ?? []).map((player, index) => (
          <div key={player.user_id} className="player-row" data-me={player.user_id === user?.id}>
            <span
              className="stripe"
              style={{ background: PLAYER_COLORS[index % PLAYER_COLORS.length] }}
            />
            <Avatar src={player.avatar} name={player.name} />
            <div className="stack" style={{ gap: 0, flex: 1, minWidth: 0 }}>
              <strong style={{ fontSize: 14 }}>
                {player.user_id === user?.id ? "You" : player.name}
              </strong>
              <span className="faint num">{gg(player.amount)} GG</span>
            </div>
            <span
              className="player-share num"
              style={{ color: player.is_winner ? "var(--win)" : "var(--text-dim)" }}
            >
              {percent(player.chance, 0)}
            </span>
          </div>
        ))}
        {!game?.players.length ? (
          <p className="faint" style={{ textAlign: "center", padding: "var(--sp-4) 0" }}>
            No one is in the pot yet — take the first seat.
          </p>
        ) : null}
      </div>
    </Screen>
  );
}

function TickerCard({
  label,
  entry,
  tone,
}: {
  label: string;
  entry: PvPHighlightEntry | null;
  tone?: "gold";
}) {
  if (!entry?.winner) {
    return (
      <div className="ticker-card">
        <div className="ticker-body">
          <span className="ticker-meta">{label}</span>
          <span className="ticker-name faint">no rounds yet</span>
        </div>
      </div>
    );
  }
  return (
    <div className="ticker-card">
      <Avatar src={entry.winner.avatar} name={entry.winner.name} />
      <div className="ticker-body">
        <span className="ticker-name">{entry.winner.name}</span>
        <span className="ticker-meta">
          {label}
          {entry.chance !== null ? ` · ${percent(entry.chance, 0)} chance` : ""}
        </span>
      </div>
      <span className="ticker-prize" style={{ color: tone === "gold" ? "var(--star)" : "var(--accent)" }}>
        +{gg(entry.prize)}
      </span>
    </div>
  );
}


function ArenaStatus({
  game,
  winner,
  secondsLeft,
}: {
  game: PvPGame | null;
  winner: { name: string; avatar: string | null; chance: number } | null;
  secondsLeft: number;
}) {
  if (game?.status === "starting") {
    return (
      <>
        <span className="headline">{secondsLeft}</span>
        <span className="sub">starting</span>
      </>
    );
  }
  if (game?.status === "spinning") {
    return (
      <>
        <span className="headline" style={{ fontSize: 20 }}>
          Drawing
        </span>
        <span className="sub">{game.players.length} players</span>
      </>
    );
  }
  if (game?.status === "finished" && winner) {
    return (
      <>
        <Avatar src={winner.avatar} name={winner.name} />
        <span className="headline" style={{ fontSize: 18, color: "var(--win)" }}>
          {gg(game.prize)}
        </span>
        <span className="sub">{percent(winner.chance, 0)} chance</span>
      </>
    );
  }
  return (
    <>
      <span className="headline" style={{ fontSize: 20 }}>
        Waiting
      </span>
      <span className="sub">{game?.players.length === 1 ? "one more player" : "place your bet"}</span>
    </>
  );
}
