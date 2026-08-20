/**
 * Round replay.
 *
 * Every round is replayable from its first bet, and nothing extra was recorded
 * to make that work: each seat carries the moment it was taken, and the round
 * carries when it locked in, spun and settled. The replay reconstructs the
 * board from those timestamps, so it cannot drift from what actually happened.
 *
 * Only the *waiting* is compressed — a lobby that sat idle for four minutes
 * plays back in a couple of seconds — while the spin runs at its true length.
 */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import type { PvPPlayer } from "@shared/index";

import { IceRink } from "@/components/IceRink";
import { PLAYER_COLORS, Wheel } from "@/components/Wheel";
import { Avatar, Card, Screen, Skeleton } from "@/components/ui";
import { api, type PvPReplayEvent } from "@/lib/api";
import { gg, percent, relative } from "@/lib/format";
import { haptics } from "@/lib/telegram";

const MAX_GAP_MS = 1200;
const COUNTDOWN_MS = 2600;

interface Step {
  at: number;
  event: PvPReplayEvent;
}

/** Lay the events out on a watchable clock: keep the order, drop the dead air. */
function schedule(events: PvPReplayEvent[], spinSeconds: number): { steps: Step[]; total: number } {
  const steps: Step[] = [];
  let clock = 0;
  let previous = 0;

  for (const event of events) {
    const gap = Math.max(0, event.at - previous) * 1000;
    if (event.type === "spin") clock += COUNTDOWN_MS;
    else if (event.type === "finished") clock += spinSeconds * 1000;
    else clock += Math.min(gap, MAX_GAP_MS);

    steps.push({ at: clock, event });
    previous = event.at;
  }
  return { steps, total: clock + 1500 };
}

export function PvpReplayPage() {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const gameId = Number(params.id);

  const { data, isLoading } = useQuery({
    queryKey: ["pvp", "replay", gameId],
    queryFn: () => api.pvpReplay(gameId),
    enabled: Number.isFinite(gameId),
  });

  const [elapsed, setElapsed] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [spinStartedAt, setSpinStartedAt] = useState<string | null>(null);
  const frame = useRef(0);
  const startedAt = useRef(0);
  const base = useRef(0);

  const spinSeconds = data?.game.spin_seconds ?? 6;
  const { steps, total } = useMemo(
    () => schedule(data?.replay.events ?? [], spinSeconds),
    [data?.replay.events, spinSeconds],
  );

  // Drive the clock.
  useEffect(() => {
    if (!playing || total === 0) return;
    startedAt.current = performance.now();
    base.current = elapsed >= total ? 0 : elapsed;

    const tick = () => {
      const value = base.current + (performance.now() - startedAt.current);
      if (value >= total) {
        setElapsed(total);
        setPlaying(false);
        return;
      }
      setElapsed(value);
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
    // `elapsed` is intentionally not a dependency: it is the output of this loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, total]);

  const seen = steps.filter((step) => step.at <= elapsed);
  const phase = seen.length ? seen[seen.length - 1].event.type : "waiting";

  // The board spins in real time from the moment the replay reaches the draw.
  useEffect(() => {
    if (phase === "spin" && !spinStartedAt) setSpinStartedAt(new Date().toISOString());
    if (phase === "waiting" || phase === "player_joined") setSpinStartedAt(null);
  }, [phase, spinStartedAt]);

  const restart = useCallback(() => {
    haptics.tap();
    setSpinStartedAt(null);
    setElapsed(0);
    setPlaying(true);
  }, []);

  if (isLoading || !data) {
    return (
      <Screen>
        <Skeleton height={120} count={2} />
      </Screen>
    );
  }

  const { game } = data;
  const joins = seen.filter((step) => step.event.type === "player_joined").map((step) => step.event);
  const pool = joins.length ? (joins[joins.length - 1].pool ?? 0) : 0;

  // Only the seats taken so far, sized against the pot at this point in time.
  const players: PvPPlayer[] = joins.map((event) => {
    const seat = game.players.find((player) => player.user_id === event.user_id);
    return {
      user_id: event.user_id as number,
      name: event.name ?? seat?.name ?? "Player",
      username: seat?.username ?? null,
      avatar: event.avatar ?? seat?.avatar ?? null,
      amount: event.amount ?? 0,
      chance: pool ? (event.amount ?? 0) / pool : 0,
      ticket_from: 0,
      ticket_to: 0,
      is_winner: phase === "finished" && game.winner_id === event.user_id,
    };
  });

  const settled = phase === "finished";
  const winner = game.players.find((player) => player.user_id === game.winner_id);
  const countdownLeft = (() => {
    const spin = steps.find((step) => step.event.type === "spin");
    if (!spin || phase !== "countdown") return 0;
    return Math.max(0, Math.ceil((spin.at - elapsed) / 1000));
  })();

  const status = (
    <>
      {phase === "countdown" ? (
        <>
          <span className="headline">{countdownLeft}</span>
          <span className="sub">starting</span>
        </>
      ) : phase === "spin" ? (
        <>
          <span className="headline" style={{ fontSize: 20 }}>
            Drawing
          </span>
          <span className="sub">{players.length} players</span>
        </>
      ) : settled && winner ? (
        <>
          <Avatar src={winner.avatar} name={winner.name} />
          <span className="headline" style={{ fontSize: 18, color: "var(--win)" }}>
            {gg(game.prize)}
          </span>
          <span className="sub">{percent(winner.chance, 0)} chance</span>
        </>
      ) : (
        <>
          <span className="headline num">{gg(pool)}</span>
          <span className="sub">{players.length ? "in the pot" : "waiting for bets"}</span>
        </>
      )}
    </>
  );

  return (
    <Screen>
      <div className="row-between">
        <div className="stack" style={{ gap: 0 }}>
          <h1>Round #{game.id}</h1>
          <span className="faint">
            {game.mode === "ice" ? "Ice arena" : "Wheel"} · {relative(game.created_at)}
          </span>
        </div>
        <span className="badge">replay</span>
      </div>

      {game.mode === "ice" ? (
        <IceRink
          players={players}
          totalPool={pool}
          winningRoll={phase === "spin" || settled ? game.winning_roll : null}
          spinAt={spinStartedAt}
          spinSeconds={spinSeconds}
        >
          {status}
        </IceRink>
      ) : (
        <Wheel
          players={players}
          totalPool={pool}
          winningRoll={phase === "spin" || settled ? game.winning_roll : null}
          spinAt={spinStartedAt}
          spinSeconds={spinSeconds}
          spinning={phase === "spin"}
        >
          {status}
        </Wheel>
      )}

      <div className="replay-bar">
        <button className="icon-btn" onClick={() => (playing ? setPlaying(false) : setPlaying(true))}>
          {playing ? "❙❙" : "▶"}
        </button>
        <div className="replay-track">
          <span style={{ width: `${total ? Math.min(elapsed / total, 1) * 100 : 0}%` }} />
        </div>
        <button className="icon-btn" onClick={restart} aria-label="Replay from the start">
          ↺
        </button>
      </div>

      <Card>
        {steps.map(({ at, event }, index) => (
          <div
            key={index}
            className="list-item"
            style={{ opacity: at <= elapsed ? 1 : 0.35, transition: "opacity 200ms" }}
          >
            <span className="faint num" style={{ width: 44 }}>
              {(at / 1000).toFixed(1)}s
            </span>
            {event.type === "player_joined" ? (
              <>
                <span
                  className="stripe"
                  style={{
                    width: 3,
                    height: 24,
                    borderRadius: 3,
                    background: PLAYER_COLORS[index % PLAYER_COLORS.length],
                  }}
                />
                <span style={{ flex: 1 }}>{event.name}</span>
                <strong className="num">+{gg(event.amount ?? 0)}</strong>
              </>
            ) : event.type === "countdown" ? (
              <span style={{ flex: 1 }} className="muted">
                Round locked in — {event.seconds}s countdown
              </span>
            ) : event.type === "spin" ? (
              <span style={{ flex: 1 }} className="muted">
                Ticket drawn
              </span>
            ) : (
              <>
                <span style={{ flex: 1 }} className="muted">
                  {winner?.name ?? "Winner"} takes the pot
                </span>
                <strong className="num" style={{ color: "var(--win)" }}>
                  +{gg(event.prize ?? 0)}
                </strong>
              </>
            )}
          </div>
        ))}
      </Card>

      <button className="btn btn-block" onClick={() => navigate("/pvp/history")}>
        Back to history
      </button>
    </Screen>
  );
}
