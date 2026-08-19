/**
 * Bet control. Clamps to the server's limits and to the player's balance so an
 * impossible bet is never sent — the backend re-checks all of it anyway.
 */

import { clamp, gg } from "@/lib/format";
import { haptics } from "@/lib/telegram";

interface Props {
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  balance: number;
  disabled?: boolean;
}

export function BetInput({ value, onChange, min, max, balance, disabled }: Props) {
  const ceiling = Math.max(min, Math.min(max, balance));

  const set = (next: number) => {
    haptics.select();
    onChange(clamp(Math.round(next), min, ceiling));
  };

  return (
    <div className="stack" style={{ gap: "var(--sp-2)" }}>
      <div className="row-between">
        <span className="faint">Bet</span>
        <span className="faint num">
          max {gg(ceiling)} GG
        </span>
      </div>

      <div className="row">
        <input
          className="input num"
          type="number"
          inputMode="numeric"
          value={value}
          min={min}
          max={ceiling}
          disabled={disabled}
          onChange={(event) => onChange(Number(event.target.value) || 0)}
          onBlur={() => set(value)}
        />
        <button className="btn btn-sm" disabled={disabled} onClick={() => set(value / 2)}>
          ½
        </button>
        <button className="btn btn-sm" disabled={disabled} onClick={() => set(value * 2)}>
          2×
        </button>
        <button className="btn btn-sm" disabled={disabled} onClick={() => set(ceiling)}>
          Max
        </button>
      </div>

      <div className="row" style={{ gap: "var(--sp-2)" }}>
        {[min, 100, 500, 1000].map((preset, index) => (
          <button
            key={`${preset}-${index}`}
            className="chip"
            data-active={value === preset}
            disabled={disabled || preset > ceiling}
            onClick={() => set(preset)}
          >
            {gg(preset)}
          </button>
        ))}
      </div>
    </div>
  );
}
