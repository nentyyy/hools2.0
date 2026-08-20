/**
 * Plinko board.
 *
 * The backend decides the whole path before the ball moves — this component
 * replays it. Between two rows the ball follows a parabola with a small bounce
 * off the peg it hits, which is what makes a scripted drop read as physics.
 * The landing slot is therefore never in doubt: it is the one the server wrote
 * down, and the animation simply arrives there.
 */

import { useEffect, useRef } from "react";

import { cssVar } from "@/lib/theme";

interface Props {
  rows: number;
  multipliers: number[];
  path: string[] | null;
  slot: number | null;
  playId: number;
  onLanded?: (slot: number) => void;
}

const ROW_MS = 105;

const palette = () => ({
  peg: "rgba(233, 219, 197, 0.2)",
  pegLit: cssVar("--accent", "#ddc9a3"),
  ball: cssVar("--accent", "#ddc9a3"),
  slotText: cssVar("--text-dim", "#a99d8a"),
  ink: cssVar("--ink", "#0a0908"),
});

function multiplierColor(value: number): string {
  if (value >= 5) return cssVar("--lose", "#d08a76");
  if (value >= 2) return cssVar("--star", "#e8c66b");
  if (value >= 1) return cssVar("--win", "#b8cf9a");
  return cssVar("--surface-3", "#29241e");
}

export function PlinkoBoard({ rows, multipliers, path, slot, playId, onLanded }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frame = useRef<number>(0);
  const landed = useRef(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const COLORS = palette();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    context.scale(dpr, dpr);

    const slotsHeight = 26;
    const boardHeight = height - slotsHeight - 10;
    const gapX = width / (rows + 2);
    const gapY = boardHeight / (rows + 1);
    const topPad = gapY * 0.9;

    const pegX = (row: number, index: number) => width / 2 + (index - row / 2) * gapX;
    const pegY = (row: number) => topPad + row * gapY;

    // Offsets the ball occupies after each decision, in half-gap units.
    const offsets: number[] = [0];
    let rights = 0;
    (path ?? []).forEach((step, index) => {
      if (step === "R") rights += 1;
      offsets.push((2 * rights - (index + 1)) / 2);
    });

    const started = performance.now();
    const duration = (path?.length ?? 0) * ROW_MS;
    landed.current = false;

    const draw = (now: number) => {
      context.clearRect(0, 0, width, height);

      const elapsed = Math.max(0, now - started);
      const progress = duration ? Math.min(elapsed / duration, 1) : 1;
      const exactRow = progress * (path?.length ?? 0);
      const currentRow = Math.floor(exactRow);
      const rowProgress = exactRow - currentRow;

      // Pegs, lit briefly as the ball passes them.
      for (let row = 0; row < rows; row += 1) {
        for (let index = 0; index <= row; index += 1) {
          const isHit =
            path !== null &&
            progress < 1 &&
            row === currentRow - 1 &&
            Math.abs(pegX(row, index) - ballX()) < gapX * 0.7 &&
            rowProgress < 0.5;
          context.beginPath();
          context.arc(pegX(row, index), pegY(row), isHit ? 4.5 : 3, 0, Math.PI * 2);
          context.fillStyle = isHit ? COLORS.pegLit : COLORS.peg;
          if (isHit) {
            context.shadowColor = COLORS.pegLit;
            context.shadowBlur = 10;
          }
          context.fill();
          context.shadowBlur = 0;
        }
      }

      // Slots share the peg spacing so a ball always lands inside one.
      const slotWidth = gapX;
      multipliers.forEach((value, index) => {
        const active = slot !== null && index === slot && progress === 1;
        const x = slotCenter(index) - slotWidth / 2;
        const y = height - slotsHeight;
        // The winning slot lifts slightly, the way a pressed key would.
        const lift = active ? 3 : 0;
        context.beginPath();
        context.roundRect(x + 1.5, y - lift, slotWidth - 3, slotsHeight - 2 + lift, 6);
        context.fillStyle = active ? multiplierColor(value) : "rgba(233, 219, 197, 0.06)";
        if (active) {
          context.shadowColor = multiplierColor(value);
          context.shadowBlur = 14;
        }
        context.fill();
        context.shadowBlur = 0;

        context.fillStyle = active ? COLORS.ink : COLORS.slotText;
        context.font = `${active ? 700 : 600} ${multipliers.length > 13 ? 8 : 9.5}px -apple-system, system-ui, sans-serif`;
        context.textAlign = "center";
        context.textBaseline = "middle";
        context.fillText(
          `${value >= 10 ? value.toFixed(0) : value.toFixed(1)}x`,
          slotCenter(index),
          y + slotsHeight / 2 - 1 - lift / 2,
        );
      });

      function slotCenter(index: number): number {
        return width / 2 + (index - rows / 2) * gapX;
      }

      function ballX(): number {
        if (!path) return width / 2;
        const from = offsets[Math.min(currentRow, offsets.length - 1)];
        const to = offsets[Math.min(currentRow + 1, offsets.length - 1)];
        const eased = rowProgress * rowProgress * (3 - 2 * rowProgress);
        return width / 2 + (from + (to - from) * eased) * gapX;
      }

      function ballY(): number {
        const base = topPad + (currentRow - 1) * gapY;
        // A short hop off the peg, then the fall to the next row.
        const hop = Math.sin(rowProgress * Math.PI) * gapY * 0.18;
        return base + rowProgress * gapY - hop;
      }

      if (path) {
        // Once it has arrived, the ball rests in the middle of its slot.
        const x = progress === 1 && slot !== null ? slotCenter(slot) : ballX();
        // It comes to rest on top of its slot, so the multiplier stays readable.
        const y = progress === 1 ? height - slotsHeight - 9 : ballY();

        context.beginPath();
        context.arc(x, y, 7, 0, Math.PI * 2);
        context.fillStyle = COLORS.ball;
        context.shadowColor = COLORS.ball;
        context.shadowBlur = 16;
        context.fill();
        context.shadowBlur = 0;
      }

      if (progress < 1) {
        frame.current = requestAnimationFrame(draw);
      } else if (!landed.current) {
        landed.current = true;
        if (slot !== null) onLanded?.(slot);
      }
    };

    frame.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame.current);
    // playId changes on every drop, which is what restarts the animation.
  }, [rows, multipliers, path, slot, playId, onLanded]);

  return <canvas ref={canvasRef} className="plinko-canvas" />;
}
