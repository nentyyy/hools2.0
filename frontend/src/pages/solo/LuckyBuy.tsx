/** LUCKY BUY — open a case; the drop lands in the inventory and can be sold. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Card, Screen, SectionTitle, Skeleton } from "@/components/ui";
import { api, newIdempotencyKey, type DropItem } from "@/lib/api";
import { gg, percent } from "@/lib/format";
import { useSession } from "@/lib/session";
import { haptics } from "@/lib/telegram";
import { useToast } from "@/lib/toast";

export function LuckyBuyPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { user, setBalance } = useSession();

  const [selected, setSelected] = useState<string | null>(null);
  const [drop, setDrop] = useState<DropItem | null>(null);

  const { data: config, isLoading } = useQuery({ queryKey: ["solo", "config"], queryFn: api.soloConfig });
  const cases = config?.lucky_buy.cases ?? [];
  const active = cases.find((item) => item.code === selected) ?? cases[0];

  const open = useMutation({
    mutationFn: () => api.playLuckyBuy({ case: active.code }, newIdempotencyKey()),
    onSuccess: (response) => {
      setBalance(response.balance);
      setDrop(response.item);
      if (response.item.gg_value >= active.price) haptics.win();
      else haptics.tap("heavy");
      void queryClient.invalidateQueries({ queryKey: ["inventory"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const sell = useMutation({
    mutationFn: (itemId: number) => api.sellItem(itemId, newIdempotencyKey()),
    onSuccess: (result) => {
      setBalance(result.balance);
      setDrop(null);
      haptics.win();
      toast.success(`Sold for ${gg(result.payout)} GG`);
      void queryClient.invalidateQueries({ queryKey: ["inventory"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (isLoading || !active) {
    return (
      <Screen>
        <Skeleton height={110} count={3} />
      </Screen>
    );
  }

  return (
    <Screen>
      <h1>Lucky Buy</h1>

      <div className="row" style={{ overflowX: "auto" }}>
        {cases.map((item) => (
          <button
            key={item.code}
            className="chip"
            data-active={item.code === active.code}
            onClick={() => {
              haptics.select();
              setSelected(item.code);
              setDrop(null);
            }}
          >
            {item.title}
          </button>
        ))}
      </div>

      <div className="stage stack" style={{ alignItems: "center" }}>
        {drop ? (
          <div className="result" data-outcome={drop.gg_value >= active.price ? "win" : "lose"} style={{ width: "100%" }}>
            <span className={`rarity-${drop.rarity}`} style={{ fontWeight: 700, letterSpacing: "0.05em" }}>
              {drop.rarity.toUpperCase()}
            </span>
            <strong style={{ fontSize: 20 }}>{drop.name}</strong>
            <span className="amount num">{gg(drop.gg_value)} GG</span>
            <button
              className="btn btn-win btn-sm"
              style={{ marginTop: "var(--sp-2)" }}
              disabled={sell.isPending}
              onClick={() => sell.mutate(drop.id)}
            >
              {sell.isPending ? "Selling…" : "Sell now"}
            </button>
            <span className="faint">or keep it in your inventory</span>
          </div>
        ) : (
          <>
            <span style={{ fontSize: 56 }}>🎁</span>
            <span className="faint">{active.title} · {gg(active.price)} GG</span>
          </>
        )}
      </div>

      <button
        className="btn btn-primary btn-block"
        disabled={open.isPending || active.price > (user?.balance ?? 0)}
        onClick={() => open.mutate()}
      >
        {open.isPending ? "Opening…" : `Open for ${gg(active.price)} GG`}
      </button>

      <SectionTitle>Contents</SectionTitle>
      <Card>
        {active.items.map((item) => (
          <div key={item.code} className="list-item">
            <span className={`rarity-${item.rarity}`} style={{ fontSize: 18 }}>
              ◆
            </span>
            <div className="stack" style={{ gap: 0, flex: 1 }}>
              <strong style={{ fontSize: 14 }}>{item.name}</strong>
              <span className="faint num">{percent(item.chance, 2)} chance</span>
            </div>
            <strong className="num">{gg(item.gg_value)} GG</strong>
          </div>
        ))}
      </Card>
    </Screen>
  );
}
