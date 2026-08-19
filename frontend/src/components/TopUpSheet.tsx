/**
 * Telegram Stars top-up.
 *
 * The backend creates the invoice (currency XTR) and returns a link; we hand
 * that link to Telegram. GG is credited by the backend when Telegram confirms
 * the payment — the client only refreshes the balance afterwards.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import type { GGPackage } from "@shared/index";

import { api, newIdempotencyKey } from "@/lib/api";
import { gg } from "@/lib/format";
import { useSession } from "@/lib/session";
import { haptics, openInvoice } from "@/lib/telegram";
import { useToast } from "@/lib/toast";

import { Sheet, Skeleton } from "./ui";

export function TopUpSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const { refresh } = useSession();
  const [pending, setPending] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["packages"],
    queryFn: api.packages,
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });

  const buy = async (pack: GGPackage) => {
    haptics.tap("medium");
    setPending(pack.code);
    try {
      const invoice = await api.createInvoice(pack.code, newIdempotencyKey());
      const status = await openInvoice(invoice.invoice_link);

      if (status === "paid") {
        // Telegram confirms to the bot, which credits through the backend; give
        // that a moment, then re-read the authoritative balance.
        haptics.win();
        toast.success("Payment received — crediting GG…");
        window.setTimeout(() => void refresh(), 1200);
        window.setTimeout(() => void refresh(), 3500);
        onClose();
      } else if (status === "failed") {
        toast.error("Payment failed. Nothing was charged.");
      } else if (status === "cancelled") {
        toast.show("Payment cancelled");
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not create the invoice");
    } finally {
      setPending(null);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title="Top up GG">
      <p className="faint" style={{ marginBottom: "var(--sp-4)" }}>
        Paid with Telegram Stars. GG lands in your balance as soon as Telegram confirms the payment.
      </p>

      {isLoading ? (
        <Skeleton height={64} count={4} />
      ) : (
        <div className="stack">
          {data?.map((pack) => (
            <button
              key={pack.code}
              className="card card-interactive row-between"
              disabled={pending !== null}
              onClick={() => void buy(pack)}
            >
              <div className="stack" style={{ gap: 2, textAlign: "left" }}>
                <strong className="num">{gg(pack.total_gg)} GG</strong>
                {pack.bonus_gg > 0 ? (
                  <span className="faint" style={{ color: "var(--win)" }}>
                    +{gg(pack.bonus_gg)} bonus
                  </span>
                ) : (
                  <span className="faint">Instant credit</span>
                )}
              </div>
              <span className="btn btn-sm btn-star num">
                {pending === pack.code ? "…" : `⭐ ${pack.stars}`}
              </span>
            </button>
          ))}
        </div>
      )}

      <p className="faint" style={{ marginTop: "var(--sp-4)" }}>
        Need help with a payment? Send /paysupport to the bot.
      </p>
    </Sheet>
  );
}
