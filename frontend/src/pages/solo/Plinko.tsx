/** PLINKO — the ball path and landing slot are computed by the backend; this
 *  screen replays them. */

import { useMutation, useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { BetInput } from "@/components/BetInput";
import { PlinkoBoard } from "@/components/PlinkoBoard";
import { Card, Screen, SectionTitle } from "@/components/ui";
import { api, newIdempotencyKey, type SoloPlayResponse } from "@/lib/api";
import { gg, multiplier } from "@/lib/format";
import { useSession } from "@/lib/session";
import { haptics } from "@/lib/telegram";
import { useToast } from "@/lib/toast";

interface PlinkoResult {
  rows: number;
  risk: string;
  path: string[];
  slot: number;
  multiplier: number;
  multipliers: number[];
}

interface Drop {
  id: number;
  result: PlinkoResult;
  bet: number;
  reward: number;
}

export function PlinkoPage() {
  const toast = useToast();
  const { user, setBalance } = useSession();

  const [bet, setBet] = useState(100);
  const [rows, setRows] = useState(12);
  const [risk, setRisk] = useState<"low" | "medium" | "high">("medium");
  const [drop, setDrop] = useState<Drop | null>(null);
  const [outcome, setOutcome] = useState<Drop | null>(null);

  const { data: config } = useQuery({ queryKey: ["solo", "config"], queryFn: api.soloConfig });
  const table = config?.plinko.tables[`${rows}:${risk}`] ?? drop?.result.multipliers ?? [];

  const play = useMutation({
    mutationFn: () => api.playPlinko({ bet, rows, risk }, newIdempotencyKey()),
    onSuccess: (response: SoloPlayResponse) => {
      const result = response.game.result as unknown as PlinkoResult;
      setBalance(response.balance);
      setOutcome(null);
      setDrop({ id: response.game.id, result, bet: response.game.bet, reward: response.game.reward });
      haptics.tap("light");
    },
    onError: (error: Error) => toast.error(error.message),
  });

  // Fired by the board the moment the ball settles, so the payout lands with it.
  const handleLanded = useCallback(() => {
    setDrop((current) => {
      if (!current) return current;
      setOutcome(current);
      if (current.reward > current.bet) haptics.win();
      else if (current.reward === 0) haptics.lose();
      else haptics.tap("medium");
      return current;
    });
  }, []);

  const reset = () => {
    setDrop(null);
    setOutcome(null);
  };

  return (
    <Screen>
      <div className="row-between">
        <h1>Plinko</h1>
        {outcome ? (
          <strong
            className="num"
            style={{ color: outcome.reward > outcome.bet ? "var(--win)" : "var(--text-dim)" }}
          >
            {multiplier(outcome.result.multiplier)} · {outcome.reward > 0 ? `+${gg(outcome.reward)}` : `−${gg(outcome.bet)}`}
          </strong>
        ) : null}
      </div>

      <div className="stage" style={{ padding: "var(--sp-2)" }}>
        <PlinkoBoard
          rows={rows}
          multipliers={table}
          path={drop?.result.path ?? null}
          slot={drop?.result.slot ?? null}
          playId={drop?.id ?? 0}
          onLanded={handleLanded}
        />
      </div>

      <Card>
        <SectionTitle>Rows</SectionTitle>
        <div className="row" style={{ marginBottom: "var(--sp-3)" }}>
          {(config?.plinko.rows ?? [8, 12, 16]).map((value) => (
            <button
              key={value}
              className="chip"
              data-active={rows === value}
              disabled={play.isPending}
              onClick={() => {
                haptics.select();
                setRows(value);
                reset();
              }}
            >
              {value}
            </button>
          ))}
        </div>

        <SectionTitle>Risk</SectionTitle>
        <div className="row" style={{ marginBottom: "var(--sp-4)" }}>
          {(["low", "medium", "high"] as const).map((value) => (
            <button
              key={value}
              className="chip"
              data-active={risk === value}
              disabled={play.isPending}
              onClick={() => {
                haptics.select();
                setRisk(value);
                reset();
              }}
            >
              {value}
            </button>
          ))}
        </div>

        <BetInput
          value={bet}
          onChange={setBet}
          min={config?.limits.min_bet ?? 10}
          max={config?.limits.max_bet ?? 50000}
          balance={user?.balance ?? 0}
          disabled={play.isPending}
        />

        <button
          className="btn btn-primary btn-block"
          style={{ marginTop: "var(--sp-3)" }}
          disabled={play.isPending || bet > (user?.balance ?? 0)}
          onClick={() => play.mutate()}
        >
          {play.isPending ? "Dropping…" : `Drop for ${gg(bet)} GG`}
        </button>
      </Card>
    </Screen>
  );
}
