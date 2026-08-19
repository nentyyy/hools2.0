/** ICE ARENA — cross tile by tile, cash out before the ice gives way. */

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { BetInput } from "@/components/BetInput";
import { Card, Screen, SectionTitle } from "@/components/ui";
import { api, newIdempotencyKey, type IceArenaState } from "@/lib/api";
import { gg, multiplier, percent } from "@/lib/format";
import { useSession } from "@/lib/session";
import { haptics } from "@/lib/telegram";
import { useToast } from "@/lib/toast";

export function IceArenaPage() {
  const toast = useToast();
  const { user, setBalance } = useSession();

  const [bet, setBet] = useState(100);
  const [state, setState] = useState<IceArenaState | null>(null);
  const [finished, setFinished] = useState<{ reward: number; bet: number; round: number } | null>(null);

  const { data: active } = useQuery({ queryKey: ["solo", "active"], queryFn: api.soloActive });
  const { data: config } = useQuery({ queryKey: ["solo", "config"], queryFn: api.soloConfig });

  useEffect(() => {
    if (active?.ice_arena && !state) setState(active.ice_arena);
  }, [active, state]);

  const play = useMutation({
    mutationFn: (body: { action: "start" | "advance" | "cash_out"; difficulty?: string }) =>
      api.playIceArena(
        {
          action: body.action,
          bet: body.action === "start" ? bet : undefined,
          game_id: body.action === "start" ? undefined : state?.game_id,
          difficulty: body.difficulty,
        },
        newIdempotencyKey(),
      ),
    onSuccess: (response) => {
      setBalance(response.balance);
      const next = response.state as IceArenaState | null;

      if (response.game.status === "active") {
        setState(next);
        setFinished(null);
        haptics.tap("medium");
        return;
      }

      setFinished({
        reward: response.game.reward,
        bet: response.game.bet,
        round: next?.round ?? 0,
      });
      setState(null);
      if (response.game.reward > 0) haptics.win();
      else haptics.lose();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const busy = play.isPending;
  const maxRounds = state?.max_rounds ?? config?.ice_arena.max_rounds ?? 12;

  return (
    <Screen>
      <h1>Ice Arena</h1>

      <div className="stage stack">
        <div className="tile-track">
          {Array.from({ length: maxRounds }, (_, index) => {
            const entry = state?.history[index] ?? null;
            const status = entry
              ? entry.survived
                ? "passed"
                : "failed"
              : index === (state?.round ?? 0)
                ? "current"
                : "ahead";
            return (
              <div key={index} className="tile" data-state={status}>
                {entry ? (entry.survived ? "✓" : "✕") : index + 1}
              </div>
            );
          })}
        </div>

        {state ? (
          <div className="row-between">
            <span className="faint num">
              tile {state.round}/{maxRounds} · {multiplier(state.multiplier)}
            </span>
            <strong className="num" style={{ color: "var(--win)" }}>
              {gg(state.potential_reward)} GG
            </strong>
          </div>
        ) : finished ? (
          <div className="result" data-outcome={finished.reward > 0 ? "win" : "lose"}>
            <span className="amount num">
              {finished.reward > 0 ? `+${gg(finished.reward)}` : `−${gg(finished.bet)}`} GG
            </span>
            <span className="faint">
              {finished.reward > 0 ? "made it across" : `the ice broke on tile ${finished.round}`}
            </span>
          </div>
        ) : (
          <p className="faint" style={{ textAlign: "center" }}>
            Pick a difficulty for every tile. Harder ice pays more.
          </p>
        )}
      </div>

      {state ? (
        <Card>
          <SectionTitle>Next tile</SectionTitle>
          <div className="stack" style={{ marginTop: "var(--sp-2)" }}>
            {state.options.map((option) => (
              <button
                key={option.difficulty}
                className="btn btn-block"
                disabled={busy}
                onClick={() => play.mutate({ action: "advance", difficulty: option.difficulty })}
              >
                <span style={{ textTransform: "capitalize" }}>{option.difficulty}</span>
                <span className="faint num">
                  {percent(option.chance, 0)} · {gg(option.reward)} GG
                </span>
              </button>
            ))}
            <button
              className="btn btn-win btn-block"
              disabled={busy || state.round === 0}
              onClick={() => play.mutate({ action: "cash_out" })}
            >
              Cash out {gg(state.potential_reward)} GG
            </button>
          </div>
        </Card>
      ) : (
        <Card>
          <BetInput
            value={bet}
            onChange={setBet}
            min={config?.limits.min_bet ?? 10}
            max={config?.limits.max_bet ?? 50000}
            balance={user?.balance ?? 0}
            disabled={busy}
          />
          <button
            className="btn btn-primary btn-block"
            style={{ marginTop: "var(--sp-3)" }}
            disabled={busy || bet > (user?.balance ?? 0)}
            onClick={() => play.mutate({ action: "start" })}
          >
            {busy ? "Starting…" : `Enter for ${gg(bet)} GG`}
          </button>
        </Card>
      )}
    </Screen>
  );
}
