/** UPGRADE — pick a multiplier; the backend rolls against the matching odds. */

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { BetInput } from "@/components/BetInput";
import { Card, Screen, SectionTitle } from "@/components/ui";
import { api, newIdempotencyKey } from "@/lib/api";
import { gg, multiplier, percent } from "@/lib/format";
import { useSession } from "@/lib/session";
import { haptics } from "@/lib/telegram";
import { useToast } from "@/lib/toast";

interface UpgradeResult {
  target: number;
  chance: number;
  roll: number;
  won: boolean;
}

export function UpgradePage() {
  const toast = useToast();
  const { user, setBalance } = useSession();

  const [bet, setBet] = useState(100);
  const [target, setTarget] = useState(2);
  const [outcome, setOutcome] = useState<{ result: UpgradeResult; reward: number } | null>(null);

  const { data: config } = useQuery({ queryKey: ["solo", "config"], queryFn: api.soloConfig });
  const edge = config?.house_edge ?? 0.04;
  const chance = (1 - edge) / target;

  const play = useMutation({
    mutationFn: () => api.playUpgrade({ bet, target }, newIdempotencyKey()),
    onSuccess: (response) => {
      const result = response.game.result as unknown as UpgradeResult;
      setBalance(response.balance);
      setOutcome({ result, reward: response.game.reward });
      if (result.won) haptics.win();
      else haptics.lose();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <Screen>
      <h1>Upgrade</h1>

      <div className="stage stack" style={{ alignItems: "center", gap: "var(--sp-2)" }}>
        <span className="faint">Target</span>
        <strong className="num" style={{ fontSize: 44, letterSpacing: "-0.04em" }}>
          {multiplier(target)}
        </strong>
        <span className="faint num">
          win chance {percent(chance)} · pays {gg(Math.round(bet * target))} GG
        </span>

        {outcome ? (
          <div className="result" data-outcome={outcome.result.won ? "win" : "lose"} style={{ width: "100%" }}>
            <span className="faint num">roll {outcome.result.roll.toFixed(6)}</span>
            <span className="amount num">
              {outcome.result.won ? `+${gg(outcome.reward)}` : `−${gg(bet)}`} GG
            </span>
            <span className="faint">needed below {outcome.result.chance.toFixed(6)}</span>
          </div>
        ) : null}
      </div>

      <Card>
        <SectionTitle>Multiplier</SectionTitle>
        <input
          className="slider"
          type="range"
          min={config?.upgrade.min_target ?? 1.1}
          max={config?.upgrade.max_target ?? 50}
          step={0.1}
          value={target}
          disabled={play.isPending}
          onChange={(event) => setTarget(Number(event.target.value))}
          style={{ margin: "var(--sp-3) 0" }}
        />
        <div className="row" style={{ marginBottom: "var(--sp-4)", flexWrap: "wrap" }}>
          {(config?.upgrade.presets ?? []).map((preset) => (
            <button
              key={preset.target}
              className="chip"
              data-active={Math.abs(target - preset.target) < 0.01}
              onClick={() => {
                haptics.select();
                setTarget(preset.target);
              }}
            >
              {preset.target}×
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
          {play.isPending ? "Rolling…" : `Upgrade ${gg(bet)} GG`}
        </button>
      </Card>
    </Screen>
  );
}
