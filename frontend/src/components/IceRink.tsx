/**
 * Ice arena — the same PvP round, told as a puck sliding across a rink.
 *
 * The field is a rectangle carved into one block per player, sized by their
 * share of the pot: a bigger stake is a bigger target, which is exactly what a
 * bigger chance means. The puck appears, bounces off the boards, loses speed
 * and stops inside the winner's block.
 *
 * The trajectory is built *backwards* from the resting point: step away from it
 * while gaining speed, reflecting off the boards, then play the recorded path in
 * reverse. Elastic reflections are time-symmetric, so what you watch is a
 * consistent slide that decelerates into precisely the spot the backend chose.
 * Nothing is decided here — the server drew the ticket before the puck moved.
 */

import { useEffect, useMemo, useRef } from "react";

import type { PvPPlayer } from "@shared/index";

import { initials } from "@/lib/format";
import { PLAYER_COLORS, cssVar } from "@/lib/theme";

interface Props {
  players: PvPPlayer[];
  totalPool: number;
  winningRoll: number | null;
  spinAt: string | null;
  spinSeconds: number;
  children?: React.ReactNode;
}

const WIDTH = 340;
const HEIGHT = 300;
const PAD = 6;
const PUCK = 10;
const STEPS = 460;
const GROWTH = 1.0088;

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface Region extends Rect {
  player: PvPPlayer;
  color: string;
}

/**
 * Recursive proportional split. The longer side is cut each time, which keeps
 * blocks close to square instead of degenerating into slivers.
 */
function carve(entries: { player: PvPPlayer; weight: number; color: string }[], rect: Rect): Region[] {
  if (entries.length === 0) return [];
  if (entries.length === 1) return [{ ...rect, player: entries[0].player, color: entries[0].color }];

  const total = entries.reduce((sum, entry) => sum + entry.weight, 0);
  let head = 0;
  let index = 0;
  // Take entries until we have about half the weight.
  while (index < entries.length - 1 && head + entries[index].weight <= total / 2) {
    head += entries[index].weight;
    index += 1;
  }
  if (index === 0) {
    head = entries[0].weight;
    index = 1;
  }

  const ratio = head / total;
  const first = entries.slice(0, index);
  const rest = entries.slice(index);

  if (rect.w >= rect.h) {
    const cut = rect.w * ratio;
    return [
      ...carve(first, { ...rect, w: cut }),
      ...carve(rest, { ...rect, x: rect.x + cut, w: rect.w - cut }),
    ];
  }
  const cut = rect.h * ratio;
  return [
    ...carve(first, { ...rect, h: cut }),
    ...carve(rest, { ...rect, y: rect.y + cut, h: rect.h - cut }),
  ];
}

interface Point {
  x: number;
  y: number;
}

function buildTrail(target: Point, seed: number): Point[] {
  const angle = (seed % 360) * (Math.PI / 180);
  let vx = Math.cos(angle) * 0.62;
  let vy = Math.sin(angle) * 0.62;
  let { x, y } = target;

  const left = PAD + PUCK;
  const right = WIDTH - PAD - PUCK;
  const top = PAD + PUCK;
  const bottom = HEIGHT - PAD - PUCK;

  const backwards: Point[] = [{ x, y }];
  for (let step = 0; step < STEPS; step += 1) {
    x -= vx;
    y -= vy;

    if (x < left) {
      x = left + (left - x);
      vx = -vx;
    } else if (x > right) {
      x = right - (x - right);
      vx = -vx;
    }
    if (y < top) {
      y = top + (top - y);
      vy = -vy;
    } else if (y > bottom) {
      y = bottom - (y - bottom);
      vy = -vy;
    }

    vx *= GROWTH;
    vy *= GROWTH;
    backwards.push({ x, y });
  }
  return backwards.reverse();
}

export function IceRink({ players, totalPool, winningRoll, spinAt, spinSeconds, children }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frame = useRef(0);
  const images = useRef(new Map<string, HTMLImageElement>());

  const regions = useMemo<Region[]>(() => {
    const total = totalPool || players.reduce((sum, p) => sum + p.amount, 0);
    if (!total) return [];
    // Biggest stake first, so the layout is stable and the largest block anchors it.
    const ordered = [...players]
      .map((player, index) => ({
        player,
        weight: player.amount,
        color: PLAYER_COLORS[index % PLAYER_COLORS.length],
      }))
      .sort((a, b) => b.weight - a.weight || a.player.user_id - b.player.user_id);

    return carve(ordered, { x: PAD, y: PAD, w: WIDTH - PAD * 2, h: HEIGHT - PAD * 2 });
  }, [players, totalPool]);

  const trail = useMemo(() => {
    if (winningRoll === null || regions.length === 0) return null;
    const winner =
      regions.find((region) => region.player.is_winner) ??
      regions[Math.floor(winningRoll * regions.length)];

    // Two independent fractions of the roll place the puck inside the block.
    const a = (winningRoll * 997) % 1;
    const b = (winningRoll * 5573) % 1;
    const target = {
      x: winner.x + winner.w * (0.25 + 0.5 * a),
      y: winner.y + winner.h * (0.25 + 0.5 * b),
    };
    return buildTrail(target, Math.floor(winningRoll * 100000));
  }, [winningRoll, regions]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = WIDTH * dpr;
    canvas.height = HEIGHT * dpr;
    context.scale(dpr, dpr);

    const endsAt = spinAt ? new Date(spinAt).getTime() + spinSeconds * 1000 : 0;

    const avatarFor = (url: string): HTMLImageElement | null => {
      const cached = images.current.get(url);
      if (cached) return cached.complete && cached.naturalWidth > 0 ? cached : null;
      const image = new Image();
      image.crossOrigin = "anonymous";
      image.src = url;
      image.onload = () => requestAnimationFrame(draw);
      images.current.set(url, image);
      return null;
    };

    function draw() {
      if (!context) return;
      context.clearRect(0, 0, WIDTH, HEIGHT);

      // Boards.
      context.beginPath();
      context.roundRect(2, 2, WIDTH - 4, HEIGHT - 4, 16);
      context.fillStyle = cssVar("--surface-1", "#141210");
      context.fill();
      context.strokeStyle = "rgba(233, 219, 197, 0.16)";
      context.lineWidth = 3;
      context.stroke();

      // One block per player.
      regions.forEach((region) => {
        context.save();
        context.beginPath();
        context.roundRect(region.x, region.y, region.w, region.h, 10);
        context.clip();

        const gradient = context.createLinearGradient(region.x, region.y, region.x + region.w, region.y + region.h);
        gradient.addColorStop(0, region.color);
        gradient.addColorStop(1, "rgba(0,0,0,0.35)");
        context.fillStyle = gradient;
        context.globalAlpha = region.player.is_winner ? 1 : 0.82;
        context.fillRect(region.x, region.y, region.w, region.h);
        context.globalAlpha = 1;

        // Ice scratches.
        context.strokeStyle = "rgba(233, 219, 197, 0.10)";
        context.lineWidth = 1;
        for (let line = 0; line < 4; line += 1) {
          const y = region.y + ((line + 1) * region.h) / 5;
          context.beginPath();
          context.moveTo(region.x + 4, y);
          context.lineTo(region.x + region.w - 4, y - 3);
          context.stroke();
        }
        context.restore();

        // The winning block keeps a lit edge once the puck has settled.
        context.beginPath();
        context.roundRect(region.x, region.y, region.w, region.h, 10);
        if (region.player.is_winner) {
          context.strokeStyle = "rgba(244, 239, 230, 0.92)";
          context.lineWidth = 3;
          context.shadowColor = region.color;
          context.shadowBlur = 18;
        } else {
          context.strokeStyle = "rgba(10, 9, 8, 0.85)";
          context.lineWidth = 2;
        }
        context.stroke();
        context.shadowBlur = 0;

        // Avatar, sized to the block it sits in.
        const radius = Math.max(12, Math.min(26, Math.min(region.w, region.h) * 0.26));
        const cx = region.x + region.w / 2;
        const cy = region.y + region.h / 2;
        const url = region.player.avatar;
        const image = url ? avatarFor(url) : null;

        context.save();
        context.beginPath();
        context.arc(cx, cy, radius, 0, Math.PI * 2);
        context.closePath();
        context.fillStyle = "rgba(10, 9, 8, 0.72)";
        context.fill();
        context.clip();
        if (image) context.drawImage(image, cx - radius, cy - radius, radius * 2, radius * 2);
        context.restore();

        if (!image) {
          context.fillStyle = "rgba(244, 239, 230, 0.92)";
          context.font = `700 ${Math.round(radius * 0.9)}px -apple-system, system-ui, sans-serif`;
          context.textAlign = "center";
          context.textBaseline = "middle";
          context.fillText(initials(region.player.name) || "?", cx, cy + 1);
        }

        context.beginPath();
        context.arc(cx, cy, radius, 0, Math.PI * 2);
        context.strokeStyle = "rgba(244, 239, 230, 0.55)";
        context.lineWidth = 2;
        context.stroke();

        // Share, when the block is big enough to read.
        if (region.h > 54 && region.w > 54) {
          context.fillStyle = "rgba(10, 9, 8, 0.85)";
          context.font = "700 11px -apple-system, system-ui, sans-serif";
          context.textAlign = "center";
          context.fillText(`${Math.round(region.player.chance * 100)}%`, cx, cy + radius + 12);
        }
      });

      let animating = false;
      if (trail) {
        const remaining = endsAt - Date.now();
        const progress =
          spinSeconds > 0 ? Math.min(Math.max(1 - remaining / (spinSeconds * 1000), 0), 1) : 1;
        const eased = 1 - (1 - progress) ** 2;
        const index = Math.min(trail.length - 1, Math.floor(eased * (trail.length - 1)));
        const puck = trail[index];

        for (let back = 1; back <= 6; back += 1) {
          const ghost = trail[Math.max(0, index - back * 4)];
          context.beginPath();
          context.arc(ghost.x, ghost.y, PUCK - back, 0, Math.PI * 2);
          context.fillStyle = `rgba(244, 239, 230, ${0.05 * (7 - back)})`;
          context.fill();
        }

        context.beginPath();
        context.arc(puck.x, puck.y, PUCK, 0, Math.PI * 2);
        context.fillStyle = cssVar("--text", "#f4efe6");
        context.shadowColor = "rgba(221, 201, 163, 0.95)";
        context.shadowBlur = 18;
        context.fill();
        context.shadowBlur = 0;

        animating = progress < 1;
      }

      if (animating) frame.current = requestAnimationFrame(draw);
    }

    frame.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame.current);
  }, [regions, trail, spinAt, spinSeconds]);

  return (
    <div className="rink-stage">
      {/* Above the boards, so the status never covers a player's block. */}
      <div className="rink-status">{children}</div>
      <canvas
        ref={canvasRef}
        className="rink-canvas"
        style={{ aspectRatio: `${WIDTH} / ${HEIGHT}` }}
      />
    </div>
  );
}
