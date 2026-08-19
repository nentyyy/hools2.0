/** Giveaways: browse, join, and watch the draw result. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { Giveaway } from "@shared/index";

import { Avatar, Badge, Card, Empty, Screen, Sheet, Skeleton } from "@/components/ui";
import { api, newIdempotencyKey } from "@/lib/api";
import { gg, timeLeft } from "@/lib/format";
import { useSession } from "@/lib/session";
import { haptics } from "@/lib/telegram";
import { useToast } from "@/lib/toast";

export function GiveawaysPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { user, setBalance } = useSession();
  const [openId, setOpenId] = useState<number | null>(null);
  const [filter, setFilter] = useState<"active" | "finished">("active");

  const { data, isLoading } = useQuery({
    queryKey: ["giveaways", filter],
    queryFn: () => api.giveaways({ status: filter, limit: 30 }),
    refetchInterval: 15000,
  });

  const detail = useQuery({
    queryKey: ["giveaway", openId],
    queryFn: () => api.giveaway(openId as number),
    enabled: openId !== null,
  });

  const join = useMutation({
    mutationFn: (id: number) => api.joinGiveaway(id, newIdempotencyKey()),
    onSuccess: (result) => {
      haptics.win();
      toast.success("You're in the draw");
      if (typeof result.balance === "number") setBalance(result.balance);
      void queryClient.invalidateQueries({ queryKey: ["giveaways"] });
      void queryClient.invalidateQueries({ queryKey: ["giveaway", openId] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <Screen>
      <h1>Giveaways</h1>

      <div className="row">
        {(["active", "finished"] as const).map((value) => (
          <button
            key={value}
            className="chip"
            data-active={filter === value}
            onClick={() => {
              haptics.select();
              setFilter(value);
            }}
          >
            {value}
          </button>
        ))}
      </div>

      {isLoading ? (
        <Skeleton height={104} />
      ) : !data?.items.length ? (
        <Empty glyph="🎁" title="Nothing here yet" hint="New drops appear regularly." />
      ) : (
        <div className="stack">
          {data.items.map((giveaway) => (
            <GiveawayCard key={giveaway.id} giveaway={giveaway} onOpen={() => setOpenId(giveaway.id)} />
          ))}
        </div>
      )}

      <Sheet open={openId !== null} onClose={() => setOpenId(null)} title={detail.data?.title}>
        {detail.isLoading || !detail.data ? (
          <Skeleton height={80} count={2} />
        ) : (
          <div className="stack">
            {detail.data.image ? (
              <img
                src={detail.data.image}
                alt={detail.data.title}
                style={{ width: "100%", borderRadius: "var(--r-md)" }}
              />
            ) : null}
            <p className="muted">{detail.data.description}</p>

            <div className="row-between">
              <span className="faint">Prize</span>
              <strong className="num">
                {detail.data.prize_type === "gg" ? `${gg(detail.data.prize_value)} GG` : detail.data.prize_type}
              </strong>
            </div>
            <div className="row-between">
              <span className="faint">Participants</span>
              <strong className="num">{detail.data.participants_count}</strong>
            </div>
            <div className="row-between">
              <span className="faint">Entry</span>
              <strong className="num">
                {detail.data.entry_cost ? `${gg(detail.data.entry_cost)} GG` : "Free"}
              </strong>
            </div>
            <div className="row-between">
              <span className="faint">{detail.data.status === "active" ? "Ends in" : "Ended"}</span>
              <strong>{detail.data.status === "active" ? timeLeft(detail.data.end_at) : "—"}</strong>
            </div>

            {detail.data.winner ? (
              <Card tight>
                <div className="row">
                  <Avatar src={detail.data.winner.avatar} name={detail.data.winner.name} />
                  <div className="stack" style={{ gap: 0 }}>
                    <span className="faint">Winner</span>
                    <strong>{detail.data.winner.name}</strong>
                  </div>
                </div>
              </Card>
            ) : null}

            {detail.data.status === "active" ? (
              <button
                className="btn btn-primary btn-block"
                disabled={
                  join.isPending ||
                  detail.data.joined ||
                  (user?.level ?? 1) < detail.data.min_level ||
                  detail.data.entry_cost > (user?.balance ?? 0)
                }
                onClick={() => join.mutate(detail.data.id)}
              >
                {detail.data.joined
                  ? "You're in"
                  : (user?.level ?? 1) < detail.data.min_level
                    ? `Level ${detail.data.min_level} required`
                    : join.isPending
                      ? "Joining…"
                      : detail.data.entry_cost
                        ? `Join for ${gg(detail.data.entry_cost)} GG`
                        : "Join for free"}
              </button>
            ) : null}
          </div>
        )}
      </Sheet>
    </Screen>
  );
}

function GiveawayCard({ giveaway, onOpen }: { giveaway: Giveaway; onOpen: () => void }) {
  return (
    <Card onClick={onOpen}>
      <div className="row-between" style={{ marginBottom: "var(--sp-2)" }}>
        <strong>{giveaway.title}</strong>
        <Badge status={giveaway.status} />
      </div>
      <div className="row-between">
        <span className="faint num">{giveaway.participants_count} joined</span>
        <span className="num" style={{ color: "var(--accent)" }}>
          {giveaway.prize_type === "gg" ? `${gg(giveaway.prize_value)} GG` : giveaway.prize_type}
        </span>
      </div>
      <div className="row-between" style={{ marginTop: "var(--sp-2)" }}>
        <span className="faint">{giveaway.status === "active" ? timeLeft(giveaway.end_at) : "finished"}</span>
        {giveaway.joined ? <span className="badge badge-live">joined</span> : null}
      </div>
    </Card>
  );
}
