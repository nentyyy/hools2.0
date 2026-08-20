/** Profile: level, stats, inventory, transactions, referrals and TON wallet. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ShieldIcon } from "@/components/icons";
import { WalletCard } from "@/components/WalletCard";
import { Avatar, Bar, Card, Empty, Screen, SectionTitle, Skeleton, Stat } from "@/components/ui";
import { api, newIdempotencyKey } from "@/lib/api";
import { gg, relative, signed, transactionLabel } from "@/lib/format";
import { useSession } from "@/lib/session";
import { haptics, shareLink } from "@/lib/telegram";
import { useToast } from "@/lib/toast";

type Tab = "inventory" | "history" | "referrals";

export function ProfilePage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { setBalance, refresh } = useSession();
  const [tab, setTab] = useState<Tab>("inventory");

  const { data, isLoading } = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const referrals = useQuery({ queryKey: ["referrals"], queryFn: api.referrals, enabled: tab === "referrals" });
  const inventory = useQuery({ queryKey: ["inventory"], queryFn: () => api.inventory({ limit: 50 }), enabled: tab === "inventory" });
  const transactions = useQuery({
    queryKey: ["transactions"],
    queryFn: () => api.transactions({ limit: 50 }),
    enabled: tab === "history",
  });

  const sell = useMutation({
    mutationFn: (id: number) => api.sellItem(id, newIdempotencyKey()),
    onSuccess: (result) => {
      haptics.win();
      setBalance(result.balance);
      toast.success(`Sold for ${gg(result.payout)} GG`);
      void queryClient.invalidateQueries({ queryKey: ["inventory"] });
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
      void refresh();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (isLoading || !data) {
    return (
      <Screen>
        <Skeleton height={120} count={3} />
      </Screen>
    );
  }

  const { user, level, stats } = data;

  return (
    <Screen>
      <div className="row">
        <Avatar src={user.avatar} name={user.first_name ?? "Player"} size="lg" />
        <div className="stack" style={{ gap: 2, flex: 1 }}>
          <h1>{user.first_name ?? "Player"}</h1>
          {user.username ? <span className="faint">@{user.username}</span> : null}
        </div>
      </div>

      <Card>
        <div className="row-between" style={{ marginBottom: "var(--sp-2)" }}>
          <strong>Level {level.level}</strong>
          <span className="faint num">{level.xp_needed} XP to go</span>
        </div>
        <Bar progress={level.progress} />
      </Card>

      <div className="grid-2">
        <Card tight>
          <Stat label="PvP wins" value={`${stats.pvp_wins}/${stats.pvp_games}`} />
        </Card>
        <Card tight>
          <Stat label="Solo wins" value={`${stats.solo_wins}/${stats.solo_games}`} />
        </Card>
        <Card tight>
          <Stat label="Total earned" value={`${gg(stats.total_earned)} GG`} tone="win" />
        </Card>
        <Card tight>
          <Stat label="Stars spent" value={`⭐ ${stats.stars_spent}`} tone="dim" />
        </Card>
      </div>

      <div className="row">
        {(["inventory", "history", "referrals"] as const).map((value) => (
          <button
            key={value}
            className="chip"
            data-active={tab === value}
            onClick={() => {
              haptics.select();
              setTab(value);
            }}
          >
            {value}
          </button>
        ))}
      </div>

      {tab === "inventory" ? (
        inventory.isLoading ? (
          <Skeleton height={56} />
        ) : !inventory.data?.items.length ? (
          <Empty glyph="🎒" title="Inventory is empty" hint="Open a Lucky Buy case to get your first drop." />
        ) : (
          <Card>
            {inventory.data.items.map((item) => (
              <div key={item.id} className="list-item">
                <span className={`rarity-${item.rarity}`} style={{ fontSize: 18 }}>
                  ◆
                </span>
                <div className="stack" style={{ gap: 0, flex: 1 }}>
                  <strong style={{ fontSize: 14 }}>{item.name}</strong>
                  <span className="faint">{item.rarity} · {relative(item.created_at)}</span>
                </div>
                <button
                  className="btn btn-sm"
                  disabled={sell.isPending || item.gg_value <= 0}
                  onClick={() => sell.mutate(item.id)}
                >
                  Sell {gg(item.gg_value)}
                </button>
              </div>
            ))}
          </Card>
        )
      ) : null}

      {tab === "history" ? (
        transactions.isLoading ? (
          <Skeleton height={56} />
        ) : !transactions.data?.items.length ? (
          <Empty glyph="🧾" title="No transactions yet" />
        ) : (
          <Card>
            {transactions.data.items.map((tx) => (
              <div key={tx.id} className="list-item">
                <div className="stack" style={{ gap: 0, flex: 1 }}>
                  <strong style={{ fontSize: 14 }}>{transactionLabel(tx.type)}</strong>
                  <span className="faint">{tx.description ?? relative(tx.created_at)}</span>
                </div>
                <div className="stack" style={{ gap: 0, alignItems: "flex-end" }}>
                  <strong className={tx.amount > 0 ? "amount-pos num" : "amount-neg num"}>
                    {signed(tx.amount)}
                  </strong>
                  <span className="faint num">{gg(tx.balance_after)}</span>
                </div>
              </div>
            ))}
          </Card>
        )
      ) : null}

      {tab === "referrals" ? (
        referrals.isLoading || !referrals.data ? (
          <Skeleton height={80} />
        ) : (
          <Card>
            <div className="row-between">
              <Stat label="Invited" value={referrals.data.invited_count} />
              <Stat label="Earned" value={`${gg(referrals.data.earnings)} GG`} tone="win" />
            </div>
            <p className="faint" style={{ margin: "var(--sp-3) 0" }}>
              You get {referrals.data.signup_bonus} GG per friend, plus {referrals.data.topup_percent}% of
              everything they top up.
            </p>
            <button
              className="btn btn-primary btn-block"
              onClick={() => {
                haptics.tap("medium");
                shareLink(referrals.data.link, "Play gg.gram with me — games, PvP and giveaways in Telegram");
              }}
            >
              Share invite link
            </button>
            <button
              className="btn btn-ghost btn-sm btn-block"
              style={{ marginTop: "var(--sp-2)" }}
              onClick={() => {
                void navigator.clipboard?.writeText(referrals.data.link);
                toast.success("Link copied");
              }}
            >
              {referrals.data.link}
            </button>

            {referrals.data.referrals.map((friend) => (
              <div key={friend.id} className="list-item">
                <Avatar src={friend.avatar} name={friend.name} />
                <div className="stack" style={{ gap: 0, flex: 1 }}>
                  <strong style={{ fontSize: 14 }}>{friend.name}</strong>
                  <span className="faint">level {friend.level} · {relative(friend.joined_at)}</span>
                </div>
              </div>
            ))}
          </Card>
        )
      ) : null}

      {user.is_admin ? (
        <button className="btn btn-block" onClick={() => navigate("/admin")}>
          <ShieldIcon size={18} /> Admin panel
        </button>
      ) : null}

      <WalletCard />

      <FairnessCard />
    </Screen>
  );
}

function FairnessCard() {
  const { data } = useQuery({ queryKey: ["fair"], queryFn: api.fairness });
  if (!data) return null;
  return (
    <>
      <SectionTitle>Provably fair</SectionTitle>
      <Card tight>
        <p className="faint" style={{ wordBreak: "break-all" }}>
          Every solo round is HMAC-SHA256(server seed, client seed:nonce). You see the hash before you
          play and the seed itself once it rotates.
          <br />
          <br />
          seed hash: {data.server_seed_hash}
          <br />
          client seed: {data.client_seed} · nonce {data.nonce}
        </p>
      </Card>
    </>
  );
}
