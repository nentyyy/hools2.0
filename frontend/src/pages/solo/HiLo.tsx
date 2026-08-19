/** HI-LO — guess the next card. Odds and payouts come from the backend. */

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { BetInput } from "@/components/BetInput";
import { Card, Screen, SectionTitle } from "@/components/ui";
import { api, newIdempotencyKey, type HiLoState } from "@/lib/api";
import { gg, multiplier, percent } from "@/lib/format";
import { useSession } from "@/lib/session";
import { haptics } from "@/lib/telegram";
import { useToast } from "@/lib/toast";

const SUIT_GLYPH: Record<string, string> = {
  spades: "♠",
  hearts: "♥",
  diamonds: "♦",
  clubs: "♣",
};

export function HiLoPage() {
  const toast = useToast();
  const { user, setBalance } = useSession();

  const [bet, setBet] = useState(100);
  const [state, setState] = useState<HiLoState | null>(null);
  const [finished, setFinished] = useState<{ reward: number; bet: number } | null>(null);

  const { data: active } = useQuery({ queryKey: ["solo", "active"], queryFn: api.soloActive });
  const { data: config } = useQuery({ queryKey: ["solo", "config"], queryFn: api.soloConfig });

  useEffect(() => {
    if (active?.hi_lo && !state) setState(active.hi_lo);
  }, [active, state]);

  const play = useMutation({
    mutationFn: (body: { action: "start" | "guess" | "cash_out"; choice?: string }) =>
      api.playHiLo(
        {
          action: body.action,
          bet: body.action === "start" ? bet : undefined,
          game_id: body.action === "start" ? undefined : state?.game_id,
          choice: body.choice,
        },
        newIdempotencyKey(),
      ),
    onSuccess: (response) => {
      setBalance(response.balance);
      const next = response.state as HiLoState | null;

      if (response.game.status === "active") {
        setState(next);
        setFinished(null);
        haptics.tap("light");
        return;
      }

      setFinished({ reward: response.game.reward, bet: response.game.bet });
      setState(null);
      if (response.game.reward > 0) haptics.win();
      else haptics.lose();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const busy = play.isPending;

  return (
    <Screen>
      <h1>Hi-Lo</h1>

      <div className="stage stack" style={{ alignItems: "center" }}>
        <div className="card-face" data-suit={state?.suit ?? "spades"}>
          {state ? `${state.card_label}${SUIT_GLYPH[state.suit ?? "spades"]}` : "?"}
        </div>

        {state ? (
          <>
            <span className="faint num">
              round {state.round}/{state.max_rounds} · {multiplier(state.multiplier)}
            </span>
            <strong className="num" style={{ fontSize: 24, color: "var(--win)" }}>
              {gg(state.potential_reward)} GG
            </strong>
          </>
        ) : finished ? (
          <div className="result" data-outcome={finished.reward > 0 ? "win" : "lose"} style={{ width: "100%" }}>
            <span className="amount num">
              {finished.reward > 0 ? `+${gg(finished.reward)}` : `−${gg(finished.bet)}`} GG
            </span>
            <span className="faint">{finished.reward > 0 ? "cashed out" : "wrong guess"}</span>
          </div>
        ) : (
          <span className="faint">Start a run to draw the first card</span>
        )}
      </div>

      {state ? (
        <Card>
          <div className="stack">
            {(["higher", "lower", "same"] as const).map((choice) => (
              <button
                key={choice}
                className={`btn btn-block ${choice === "higher" ? "btn-primary" : ""}`}
                disabled={busy}
                onClick={() => play.mutate({ action: "guess", choice })}
              >
                <span style={{ textTransform: "capitalize" }}>{choice}</span>
                <span className="faint num">
                  {percent(state.odds[choice]?.chance ?? 0, 0)} · {multiplier(state.odds[choice]?.multiplier ?? 0)}
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
            {busy ? "Dealing…" : `Deal for ${gg(bet)} GG`}
          </button>
        </Card>
      )}

      {state && state.history.length > 0 ? (
        <>
          <SectionTitle>This run</SectionTitle>
          <Card>
            {state.history.map((entry) => (
              <div key={entry.round} className="list-item">
                <span className="faint">#{entry.round}</span>
                <span style={{ flex: 1 }}>
                  {entry.card} → {entry.next_card} · {entry.choice}
                </span>
                <strong className={entry.won ? "amount-pos num" : "amount-neg num"}>
                  {multiplier(entry.step)}
                </strong>
              </div>
            ))}
          </Card>
        </>
      ) : null}
    </Screen>
  );
}
