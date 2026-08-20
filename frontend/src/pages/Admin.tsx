/**
 * Admin panel.
 *
 * Every action here goes through the same guarded endpoints as the rest of the
 * API — a balance grant is an ordinary ledger entry of type `admin_adjustment`,
 * visible in the user's own history. Nothing here writes a balance directly.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { User } from "@shared/index";

import { Avatar, Card, Empty, Screen, SectionTitle, Skeleton, Stat } from "@/components/ui";
import { api, newIdempotencyKey } from "@/lib/api";
import { gg } from "@/lib/format";
import { useSession } from "@/lib/session";
import { haptics } from "@/lib/telegram";
import { useToast } from "@/lib/toast";

const GRANT_PRESETS = [1_000, 10_000, 100_000, 1_000_000];

export function AdminPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { user } = useSession();

  const [term, setTerm] = useState("");
  const [amount, setAmount] = useState(1_000_000);
  const [selected, setSelected] = useState<User | null>(null);

  const stats = useQuery({ queryKey: ["admin", "stats"], queryFn: api.adminStats });
  const search = useQuery({
    queryKey: ["admin", "users", term],
    queryFn: () => api.adminUsers({ q: term, limit: 20 }),
    enabled: term.trim().length >= 2,
  });

  const grant = useMutation({
    mutationFn: (target: User) =>
      api.adminAdjustBalance(target.id, amount, `Granted by admin #${user?.id}`, newIdempotencyKey()),
    onSuccess: (result, target) => {
      haptics.win();
      toast.success(`${target.username ?? target.first_name}: ${gg(result.balance)} GG`);
      void queryClient.invalidateQueries({ queryKey: ["admin"] });
      setSelected(null);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (!user?.is_admin) {
    return (
      <Screen>
        <Empty glyph="⌁" title="Admins only" hint="This account has no administrator rights." />
      </Screen>
    );
  }

  return (
    <Screen>
      <h1>Admin</h1>

      {stats.isLoading ? (
        <Skeleton height={72} count={1} />
      ) : stats.data ? (
        <div className="grid-2">
          <Card tight>
            <Stat label="Players" value={stats.data.users.total} />
          </Card>
          <Card tight>
            <Stat label="Active 24h" value={stats.data.users.active_24h} />
          </Card>
          <Card tight>
            <Stat label="GG in circulation" value={gg(stats.data.economy.gg_circulating)} />
          </Card>
          <Card tight>
            <Stat label="Stars collected" value={`⭐ ${stats.data.economy.stars_collected}`} tone="dim" />
          </Card>
        </div>
      ) : null}

      <SectionTitle>Grant GG</SectionTitle>
      <Card>
        <input
          className="input"
          placeholder="username, name or telegram id"
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          autoCapitalize="none"
          autoCorrect="off"
        />

        <div className="row" style={{ margin: "var(--sp-3) 0", flexWrap: "wrap" }}>
          {GRANT_PRESETS.map((preset) => (
            <button
              key={preset}
              className="chip"
              data-active={amount === preset}
              onClick={() => {
                haptics.select();
                setAmount(preset);
              }}
            >
              {gg(preset)}
            </button>
          ))}
        </div>

        {term.trim().length < 2 ? (
          <p className="faint">Type at least two characters to search.</p>
        ) : search.isLoading ? (
          <Skeleton height={52} count={2} />
        ) : !search.data?.items.length ? (
          <p className="faint">No players match “{term}”.</p>
        ) : (
          <div className="stack" style={{ gap: "var(--sp-2)" }}>
            {search.data.items.map((found) => (
              <div key={found.id} className="player-row" data-me={selected?.id === found.id}>
                <Avatar src={found.avatar} name={found.first_name ?? found.username ?? "Player"} />
                <div className="stack" style={{ gap: 0, flex: 1, minWidth: 0 }}>
                  <strong style={{ fontSize: 14 }}>
                    {found.username ? `@${found.username}` : found.first_name ?? `#${found.id}`}
                  </strong>
                  <span className="faint num">
                    {gg(found.balance)} GG · id {found.telegram_id}
                  </span>
                </div>
                <button
                  className="btn btn-sm btn-primary"
                  disabled={grant.isPending}
                  onClick={() => {
                    setSelected(found);
                    grant.mutate(found);
                  }}
                >
                  +{gg(amount)}
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>

      <p className="faint">
        Grants are recorded in the ledger as admin adjustments and appear in the player's own
        transaction history.
      </p>
    </Screen>
  );
}
