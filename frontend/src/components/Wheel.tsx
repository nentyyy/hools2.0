/**
 * PvP wheel.
 *
 * Each player owns a slice sized by their share of the pot, which is also their
 * chance of winning. When the backend has drawn a ticket it hands us
 * `winningRoll` — a number in [0, 1) — and the wheel spins so that exact point
 * comes to rest under the pointer. The animation is presentation only: the
 * result was decided and written down server-side before the wheel moved.
 *
 * A player who opens the screen mid-spin gets the remaining time as the
 * transition duration, so everyone sees it land at the same moment.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import type { PvPPlayer } from "@shared/index";

import { initials } from "@/lib/format";

export const PLAYER_COLORS = [
  "#55c8ff",
  "#6ff0ad",
  "#ffc93f",
  "#a98bff",
  "#ff6470",
  "#5ad1a4",
  "#ff9f43",
  "#4dd0e1",
  "#f06292",
  "#9ccc65",
  "#7986cb",
  "#ffb74d",
];

const SIZE = 300;
const CENTER = SIZE / 2;
const RADIUS = 142;
const HOLE = 78;
const AVATAR_RING = (RADIUS + HOLE) / 2;
const FULL_TURNS = 6;

interface Props {
  players: PvPPlayer[];
  totalPool: number;
  winningRoll: number | null;
  spinAt: string | null;
  spinSeconds: number;
  spinning: boolean;
  children?: React.ReactNode;
}

interface Slice {
  player: PvPPlayer;
  from: number;
  to: number;
  color: string;
}

function polar(angle: number, radius: number): [number, number] {
  const rad = ((angle - 90) * Math.PI) / 180;
  return [CENTER + radius * Math.cos(rad), CENTER + radius * Math.sin(rad)];
}

function arcPath(from: number, to: number): string {
  // A full circle cannot be drawn as a single arc; nudge it just short of 360.
  const sweep = Math.min(to - from, 359.999);
  const [x1, y1] = polar(from, RADIUS);
  const [x2, y2] = polar(from + sweep, RADIUS);
  const large = sweep > 180 ? 1 : 0;
  return `M ${CENTER} ${CENTER} L ${x1} ${y1} A ${RADIUS} ${RADIUS} 0 ${large} 1 ${x2} ${y2} Z`;
}

export function Wheel({
  players,
  totalPool,
  winningRoll,
  spinAt,
  spinSeconds,
  spinning,
  children,
}: Props) {
  const [rotation, setRotation] = useState(0);
  const [duration, setDuration] = useState(0);
  const settled = useRef<number | null>(null);

  const slices = useMemo<Slice[]>(() => {
    const total = totalPool || players.reduce((sum, p) => sum + p.amount, 0);
    if (!total) return [];
    let cursor = 0;
    return players.map((player, index) => {
      const from = (cursor / total) * 360;
      cursor += player.amount;
      return {
        player,
        from,
        to: (cursor / total) * 360,
        color: PLAYER_COLORS[index % PLAYER_COLORS.length],
      };
    });
  }, [players, totalPool]);

  useEffect(() => {
    if (winningRoll === null) {
      settled.current = null;
      setDuration(0);
      setRotation(0);
      return;
    }
    if (settled.current === winningRoll) return;
    settled.current = winningRoll;

    // Bring the winning point to the pointer at the top.
    const target = FULL_TURNS * 360 - winningRoll * 360;
    const endsAt = spinAt ? new Date(spinAt).getTime() + spinSeconds * 1000 : Date.now();
    const remaining = Math.max(0, Math.min(endsAt - Date.now(), spinSeconds * 1000));

    setDuration(remaining);
    // Two frames: the first commits the starting rotation, the second animates.
    requestAnimationFrame(() => requestAnimationFrame(() => setRotation(target)));
  }, [winningRoll, spinAt, spinSeconds]);

  const transform = `rotate(${rotation}deg)`;
  const transition = duration ? `transform ${duration}ms cubic-bezier(0.12, 0.72, 0.16, 1)` : "none";

  return (
    <div className="wheel-stage" data-spinning={spinning}>
      <div className="wheel-pointer" />

      <div className="wheel-rotor" style={{ transform, transition }}>
        <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="wheel-svg" aria-hidden="true">
          {slices.length === 0 ? (
            <circle cx={CENTER} cy={CENTER} r={RADIUS} fill="var(--surface-2)" />
          ) : (
            slices.map((slice) => (
              <path
                key={slice.player.user_id}
                d={arcPath(slice.from, slice.to)}
                fill={slice.color}
                stroke="var(--ink)"
                strokeWidth={slices.length > 1 ? 2 : 0}
              />
            ))
          )}
          <circle cx={CENTER} cy={CENTER} r={HOLE} fill="var(--ink)" />
          <circle
            cx={CENTER}
            cy={CENTER}
            r={RADIUS}
            fill="none"
            stroke="rgba(255,255,255,0.08)"
            strokeWidth="2"
          />
        </svg>

        {slices.map((slice) => {
          const mid = (slice.from + slice.to) / 2;
          const [x, y] = polar(mid, AVATAR_RING);
          return (
            <span
              key={slice.player.user_id}
              className="wheel-avatar"
              style={{
                left: `${(x / SIZE) * 100}%`,
                top: `${(y / SIZE) * 100}%`,
                // Counter-rotate so faces stay upright while the wheel turns.
                transform: `translate(-50%, -50%) rotate(${-rotation}deg)`,
                transition,
                borderColor: slice.color,
              }}
            >
              {slice.player.avatar ? (
                <img src={slice.player.avatar} alt={slice.player.name} loading="lazy" />
              ) : (
                initials(slice.player.name) || "?"
              )}
            </span>
          );
        })}
      </div>

      <div className="wheel-center">{children}</div>
    </div>
  );
}
