/** PLINKO — the ball path and landing slot are computed by the backend; this
 *  screen replays them. */

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { BetInput } from "@/components/BetInput";
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

export function PlinkoPage() {
  const toast = useToast();
  const { user, setBalance } = useSession();

  const [bet, setBet] = useState(100);
  const [rows, setRows] = useState(12);
  const [risk, setRisk] = useState<"low" | "medium" | "high">("medium");
  const [result, setResult] = useState<PlinkoResult | null>(null);
  const [step, setStep] = useState(-1);
  const [reward, setReward] = useState<number | null>(null);
  const timers = useRef<number[]>([]);

  const { data: config } = useQuery({ queryKey: ["solo", "config"], queryFn: api.soloConfig });
  const table = config?.plinko.tables[`${rows}:${risk}`] ?? result?.multipliers ?? [];

  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);

  const play = useMutation({
    mutationFn: () => api.playPlinko({ bet, rows, risk }, newIdempotencyKey()),
    onSuccess: (response: SoloPlayResponse) => {
      const payload = response.game.result as unknown as PlinkoResult;
      setBalance(response.balance);
      setResult(payload);
      setReward(null);
      setStep(-1);

      // Replay the server's path one peg row at a time.
      timers.current.forEach(window.clearTimeout);
      timers.current = payload.path.map((_, index) =>
        window.setTimeout(() => {
          setStep(index);
          haptics.tap("light");
        }, 90 * (index + 1)),
      );
      timers.current.push(
        window.setTimeout(
          () => {
            setReward(response.game.reward);
            if (response.game.reward > bet) haptics.win();
            else if (response.game.reward === 0) haptics.lose();
          },
          90 * (payload.path.length + 1),
        ),
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <Screen>
      <h1>Plinko</h1>

      <div className="stage">
        <div className="peg-grid">
          {Array.from({ length: rows }, (_, rowIndex) => (
            <div key={rowIndex} className="peg-row">
              {Array.from({ length: rowIndex + 2 }, (_, pegIndex) => (
                <span
                  key={pegIndex}
                  className="peg"
                  data-lit={
                    result !== null &&
                    step >= rowIndex &&
                    pegIndex === result.path.slice(0, rowIndex + 1).filter((s) => s === "R").length
                  }
                />
              ))}
            </div>
          ))}
        </div>

        <div className="plinko-slots">
          {table.map((value, index) => (
            <div
              key={index}
              className="plinko-slot num"
              data-hit={reward !== null && result?.slot === index}
            >
              {value.toFixed(value >= 10 ? 0 : 1)}×
            </div>
          ))}
        </div>
      </div>

      {reward !== null && result ? (
        <div className="result" data-outcome={reward > bet ? "win" : "lose"}>
          <span className="faint">{multiplier(result.multiplier)}</span>
          <span className="amount num">{reward > 0 ? `+${gg(reward)}` : `−${gg(bet)}`} GG</span>
        </div>
      ) : null}

      <Card>
        <SectionTitle>Rows</SectionTitle>
        <div className="row" style={{ marginBottom: "var(--sp-3)" }}>
          {(config?.plinko.rows ?? [8, 12, 16]).map((value) => (
            <button
              key={value}
              className="chip"
              data-active={rows === value}
              onClick={() => {
                haptics.select();
                setRows(value);
                setResult(null);
                setReward(null);
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
              onClick={() => {
                haptics.select();
                setRisk(value);
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
