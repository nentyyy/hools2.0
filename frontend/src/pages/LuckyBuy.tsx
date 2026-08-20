/**
 * Lucky Buy — a bet on one gift at odds you choose.
 *
 * The slider sets the win chance; the stake is derived from it and the gift's
 * value, exactly as the backend derives it, so the price on screen is the price
 * charged. Every outcome comes back from the server with the roll that produced
 * it, and the bar below simply shows where that roll fell.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { CloverReel } from "@/components/CloverReel";
import { Card, Screen, Skeleton } from "@/components/ui";
import { api, newIdempotencyKey, type ShopGift } from "@/lib/api";
import { gg, multiplier, percent } from "@/lib/format";
import { useSession } from "@/lib/session";
import { haptics } from "@/lib/telegram";
import { useToast } from "@/lib/toast";

interface Outcome {
  playId: number;
  roll: number;
  won: boolean;
  stake: number;
  itemId: number | null;
}

const SKIP_KEY = "gg.skip-animation";

export function LuckyBuyPage() {
  const params = useParams<{ code: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { user, setBalance } = useSession();

  const [chance, setChance] = useState(0.05);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [skip, setSkip] = useState(() => localStorage.getItem(SKIP_KEY) === "1");

  const { data, isLoading } = useQuery({ queryKey: ["shop"], queryFn: () => api.shop() });

  const gifts = data?.gifts ?? [];
  const index = Math.max(0, gifts.findIndex((gift) => gift.code === params.code));
  const gift: ShopGift | undefined = gifts[index];

  const houseEdge = data?.house_edge ?? 0.04;
  const stake = useMemo(
    () => (gift ? Math.max(1, Math.ceil((gift.gg_value * chance) / (1 - houseEdge))) : 0),
    [gift, chance, houseEdge],
  );

  // Switching gifts starts a clean attempt.
  useEffect(() => {
    setOutcome(null);
    setRevealed(false);
  }, [params.code]);

  const play = useMutation({
    mutationFn: () => api.playLuckyBuy({ gift: gift!.code, chance }, newIdempotencyKey()),
    onSuccess: (response) => {
      const result = response.game.result as unknown as {
        roll: number;
        won: boolean;
        stake: number;
        item_id: number | null;
      };
      setBalance(response.balance);
      setRevealed(false);
      setOutcome({
        playId: response.game.id,
        roll: result.roll,
        won: result.won,
        stake: result.stake,
        itemId: result.item_id,
      });
      haptics.tap("medium");
      void queryClient.invalidateQueries({ queryKey: ["inventory"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const sell = useMutation({
    mutationFn: (itemId: number) => api.sellItem(itemId, newIdempotencyKey()),
    onSuccess: (result) => {
      setBalance(result.balance);
      setOutcome((current) => (current ? { ...current, itemId: null } : current));
      haptics.win();
      toast.success(`Sold for ${gg(result.payout)} GG`);
      void queryClient.invalidateQueries({ queryKey: ["inventory"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const handleSettled = useCallback(() => {
    setRevealed(true);
    setOutcome((current) => {
      if (current) current.won ? haptics.win() : haptics.lose();
      return current;
    });
  }, []);

  if (isLoading || !gift) {
    return (
      <Screen>
        <Skeleton height={180} count={2} />
      </Screen>
    );
  }

  const state = !outcome || !revealed ? "idle" : outcome.won ? "won" : "lost";
  const step = (target: number) => navigate(`/shop/${gifts[(target + gifts.length) % gifts.length].code}`);

  return (
    <Screen>
      <div className="gift-switcher">
        <button onClick={() => step(index - 1)} aria-label="Previous gift">
          ‹
        </button>
        <div className="stack" style={{ gap: 0, textAlign: "center", flex: 1 }}>
          <strong>{gift.name}</strong>
          <span className={`faint rarity-${gift.rarity}`}>{gift.rarity}</span>
        </div>
        <button onClick={() => step(index + 1)} aria-label="Next gift">
          ›
        </button>
      </div>

      <div className="gift-hero" data-state={state}>
        <span className="gift-glyph">{gift.glyph}</span>
        <strong className="num" style={{ fontSize: 20, color: "var(--accent)" }}>
          {gg(gift.gg_value)} GG
        </strong>
        {state === "won" ? (
          <>
            <span style={{ color: "var(--win)", fontWeight: 700 }}>Yours</span>
            {outcome?.itemId ? (
              <button
                className="btn btn-sm btn-win"
                disabled={sell.isPending}
                onClick={() => sell.mutate(outcome.itemId as number)}
              >
                {sell.isPending ? "Selling…" : `Sell for ${gg(gift.gg_value)} GG`}
              </button>
            ) : (
              <span className="faint">sold — check your balance</span>
            )}
          </>
        ) : state === "lost" ? (
          <span style={{ color: "var(--lose)", fontWeight: 700 }}>−{gg(outcome!.stake)} GG</span>
        ) : (
          <span className="faint">in your inventory if you win it</span>
        )}
      </div>

      <Card>
        <div className="row-between" style={{ marginBottom: "var(--sp-2)" }}>
          <span className="section-title">Win chance</span>
          <span className="chip" data-active="true">
            {percent(chance, 0)}
          </span>
        </div>

        <input
          className="slider"
          type="range"
          min={Math.round(gift.min_chance * 100)}
          max={Math.round(gift.max_chance * 100)}
          step={1}
          value={Math.round(chance * 100)}
          disabled={play.isPending}
          onChange={(event) => {
            setChance(Number(event.target.value) / 100);
            setOutcome(null);
          }}
        />

        <div style={{ margin: "var(--sp-4) 0 var(--sp-3)" }}>
          <CloverReel
            chance={chance}
            roll={outcome?.roll ?? null}
            playId={outcome?.playId ?? 0}
            skip={skip}
            onSettled={handleSettled}
          />
          <p className="faint" style={{ marginTop: 6, textAlign: "center" }}>
            {Math.round(chance * 100)} clovers out of 100 tiles
            {outcome && revealed ? ` · roll ${outcome.roll.toFixed(4)}` : ""}
          </p>
        </div>

        <div className="payout-row">
          <span className="faint">Possible win</span>
          <strong className="num">
            <span className="faint">({multiplier(gift.gg_value / Math.max(stake, 1))})</span>{" "}
            {gg(gift.gg_value)} GG
          </strong>
        </div>
        <div className="payout-row">
          <span className="faint">Your balance</span>
          <strong className="num">{gg(user?.balance ?? 0)} GG</strong>
        </div>
        <div className="payout-row">
          <span className="faint">Skip animation</span>
          <button
            className="switch"
            data-on={skip}
            aria-label="Skip animation"
            onClick={() => {
              const next = !skip;
              setSkip(next);
              localStorage.setItem(SKIP_KEY, next ? "1" : "0");
              haptics.select();
            }}
          />
        </div>

        <button
          className="btn btn-primary btn-block"
          style={{ marginTop: "var(--sp-4)" }}
          disabled={play.isPending || stake > (user?.balance ?? 0)}
          onClick={() => play.mutate()}
        >
          {play.isPending
            ? "Rolling…"
            : stake > (user?.balance ?? 0)
              ? "Not enough GG"
              : `Try your luck · ${gg(stake)} GG`}
        </button>
      </Card>
    </Screen>
  );
}
