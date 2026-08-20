/**
 * Clover reel.
 *
 * The strip is the probability, made countable: one hundred tiles, of which
 * exactly as many carry a clover as the percentage the player bought. The
 * backend's roll picks a tile — bucket `floor(roll * 100)` — and the tile it
 * lands on carries a clover precisely when `roll < chance`. So the reel is not
 * a dramatisation of the odds, it *is* the comparison the server made, and the
 * clovers are scattered by a seeded shuffle only so the strip does not read as
 * "all the wins are at the front".
 */

import { useEffect, useMemo, useRef, useState } from "react";

const BUCKETS = 100;
const COPIES = 2;
const TILE = 54;
const GAP = 6;
const STRIDE = TILE + GAP;

interface Props {
  chance: number;
  roll: number | null;
  playId: number;
  skip: boolean;
  durationMs?: number;
  onSettled?: () => void;
}

/** Small deterministic PRNG so every render of one round shuffles identically. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function CloverIcon({ dim }: { dim?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true">
      <path
        d="M12 21.5c0-4 .6-6 2.2-7.4 1.6 1.2 3.6 1 4.8-.3 1.2-1.4 1-3.5-.4-4.6-1.4-1.1-3.4-.8-4.5.6.5-1.8-.4-3.6-2.1-4.3-1.7.7-2.6 2.5-2.1 4.3-1.1-1.4-3.1-1.7-4.5-.6-1.4 1.1-1.6 3.2-.4 4.6 1.2 1.3 3.2 1.5 4.8.3C11.4 15.5 12 17.5 12 21.5z"
        fill={dim ? "currentColor" : "var(--win)"}
        opacity={dim ? 0.25 : 1}
      />
    </svg>
  );
}

export function CloverReel({ chance, roll, playId, skip, durationMs = 3200, onSettled }: Props) {
  const [offset, setOffset] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const viewport = useRef<HTMLDivElement>(null);
  const played = useRef(0);

  const clovers = Math.max(1, Math.round(chance * BUCKETS));

  // position -> is a clover, plus bucket -> position, from one seeded shuffle.
  const { isClover, positionOfBucket } = useMemo(() => {
    const positions = Array.from({ length: BUCKETS }, (_, index) => index);
    const random = mulberry32(playId * 2654435761 + clovers);
    for (let i = positions.length - 1; i > 0; i -= 1) {
      const j = Math.floor(random() * (i + 1));
      [positions[i], positions[j]] = [positions[j], positions[i]];
    }
    const flags = new Array<boolean>(BUCKETS).fill(false);
    // Buckets below the chance are the winning ones; they keep that meaning
    // wherever the shuffle puts them.
    for (let bucket = 0; bucket < clovers; bucket += 1) flags[positions[bucket]] = true;
    return { isClover: flags, positionOfBucket: positions };
  }, [playId, clovers]);

  useEffect(() => {
    if (roll === null) {
      setSpinning(false);
      setOffset(0);
      return;
    }
    if (played.current === playId) return;
    played.current = playId;

    const width = viewport.current?.clientWidth ?? 320;
    const bucket = Math.min(BUCKETS - 1, Math.floor(roll * BUCKETS));
    // Land in the last copy so the strip has room to build up speed.
    const position = positionOfBucket[bucket] + BUCKETS * (COPIES - 1);
    const target = position * STRIDE + TILE / 2 - width / 2;

    if (skip) {
      setSpinning(false);
      setOffset(target);
      onSettled?.();
      return;
    }

    setSpinning(false);
    setOffset(0);
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        setSpinning(true);
        setOffset(target);
      }),
    );
    const timer = window.setTimeout(() => {
      setSpinning(false);
      onSettled?.();
    }, durationMs);
    return () => window.clearTimeout(timer);
  }, [roll, playId, skip, durationMs, positionOfBucket, onSettled]);

  const landedBucket = roll === null ? null : Math.min(BUCKETS - 1, Math.floor(roll * BUCKETS));
  const landedPosition =
    landedBucket === null ? null : positionOfBucket[landedBucket] + BUCKETS * (COPIES - 1);

  return (
    <div className="clover-reel" ref={viewport}>
      <div className="reel-marker reel-marker-top" />
      <div className="reel-marker reel-marker-bottom" />
      <div className="reel-fade reel-fade-left" />
      <div className="reel-fade reel-fade-right" />

      <div
        className="clover-strip"
        style={{
          transform: `translate3d(${-offset}px, 0, 0)`,
          transition: spinning ? `transform ${durationMs}ms cubic-bezier(0.07, 0.72, 0.12, 1)` : "none",
        }}
      >
        {Array.from({ length: BUCKETS * COPIES }, (_, index) => {
          const clover = isClover[index % BUCKETS];
          return (
            <div
              key={index}
              className="clover-tile"
              data-clover={clover}
              data-landed={!spinning && landedPosition === index}
            >
              <CloverIcon dim={!clover} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
