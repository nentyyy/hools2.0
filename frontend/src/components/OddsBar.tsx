/**
 * Odds bar.
 *
 * The strip is the probability itself: the lit part is the chance the player
 * bought, and the marker sweeps to the roll the backend returned. Landing
 * inside the lit part is the win — the same comparison the server made, drawn
 * at a size you can see.
 */

import { useEffect, useState } from "react";

interface Props {
  chance: number;
  roll: number | null;
  playId: number;
  skip: boolean;
  durationMs?: number;
  onSettled?: () => void;
}

export function OddsBar({ chance, roll, playId, skip, durationMs = 2200, onSettled }: Props) {
  const [position, setPosition] = useState<number | null>(null);
  const [sweeping, setSweeping] = useState(false);

  useEffect(() => {
    if (roll === null) {
      setPosition(null);
      return;
    }
    if (skip) {
      setSweeping(false);
      setPosition(roll);
      onSettled?.();
      return;
    }

    setSweeping(false);
    setPosition(0);
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        setSweeping(true);
        setPosition(roll);
      }),
    );
    const timer = window.setTimeout(() => {
      // Ending the sweep is what colours the marker by the outcome.
      setSweeping(false);
      onSettled?.();
    }, durationMs);
    return () => window.clearTimeout(timer);
  }, [roll, playId, skip, durationMs, onSettled]);

  const won = roll !== null && roll < chance;

  return (
    <div className="odds">
      <div className="odds-track">
        <span className="odds-win" style={{ width: `${Math.min(chance, 1) * 100}%` }} />
        {position !== null ? (
          <span
            className="odds-marker"
            data-outcome={sweeping ? "pending" : won ? "win" : "lose"}
            style={{
              left: `${Math.min(Math.max(position, 0), 1) * 100}%`,
              transition: sweeping
                ? `left ${durationMs}ms cubic-bezier(0.1, 0.75, 0.15, 1)`
                : "none",
            }}
          />
        ) : null}
      </div>
      <div className="odds-legend">
        <span style={{ color: "var(--win)" }}>win {Math.round(chance * 100)}%</span>
        <span className="faint num">
          {position !== null && !sweeping ? `roll ${position.toFixed(4)}` : " "}
        </span>
      </div>
    </div>
  );
}
