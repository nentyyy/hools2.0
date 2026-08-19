/**
 * TON Connect.
 *
 * The wallet stays in the user's own app: we only receive its public address
 * and a `ton_proof` signature, which the backend verifies against a challenge
 * it issued. No key material ever reaches our servers.
 *
 * TON is used for wallet-linked blockchain features only — digital goods inside
 * the Mini App are sold for Telegram Stars, as Telegram requires.
 */

import { useTonConnectUI, useTonWallet } from "@tonconnect/ui-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { Card, SectionTitle } from "@/components/ui";
import { api, newIdempotencyKey } from "@/lib/api";
import { relative, shortAddress } from "@/lib/format";
import { haptics } from "@/lib/telegram";
import { useToast } from "@/lib/toast";

export function WalletCard() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [tonConnectUI] = useTonConnectUI();
  const wallet = useTonWallet();
  const submitted = useRef<string | null>(null);

  const { data } = useQuery({ queryKey: ["ton", "wallet"], queryFn: api.tonWallet });
  const { data: history } = useQuery({ queryKey: ["ton", "transactions"], queryFn: api.tonTransactions });

  // Ask TON Connect to sign our challenge, so the proof can be verified server side.
  useEffect(() => {
    if (!data?.proof_payload || wallet) return;
    void tonConnectUI.setConnectRequestParameters({
      state: "ready",
      value: { tonProof: data.proof_payload },
    });
  }, [data?.proof_payload, tonConnectUI, wallet]);

  // Hand the address and proof to the backend exactly once per connection.
  useEffect(() => {
    if (!wallet || submitted.current === wallet.account.address) return;
    submitted.current = wallet.account.address;

    const proofItem = (wallet as { connectItems?: { tonProof?: { proof?: unknown } } }).connectItems?.tonProof;
    const proof =
      proofItem && "proof" in proofItem
        ? (proofItem.proof as {
            timestamp: number;
            domain: { lengthBytes?: number; value: string };
            signature: string;
            payload: string;
          })
        : undefined;

    void api
      .tonConnect(
        {
          address: wallet.account.address,
          public_key: wallet.account.publicKey,
          chain: wallet.account.chain,
          wallet_name: wallet.device.appName,
          proof,
        },
        newIdempotencyKey(),
      )
      .then(() => {
        haptics.win();
        toast.success("Wallet connected");
        void queryClient.invalidateQueries({ queryKey: ["ton"] });
      })
      .catch((error: Error) => {
        toast.error(error.message);
        void tonConnectUI.disconnect();
      });
  }, [wallet, queryClient, toast, tonConnectUI]);

  const disconnect = async () => {
    try {
      await tonConnectUI.disconnect();
    } catch {
      /* the wallet may already be gone */
    }
    submitted.current = null;
    await api.tonDisconnect(newIdempotencyKey()).catch(() => undefined);
    void queryClient.invalidateQueries({ queryKey: ["ton"] });
    toast.show("Wallet disconnected");
  };

  return (
    <>
      <SectionTitle>TON wallet</SectionTitle>
      <Card>
        {data?.connected && data.wallet ? (
          <div className="stack">
            <div className="row-between">
              <div className="stack" style={{ gap: 0 }}>
                <strong>{data.wallet.wallet_name ?? "TON wallet"}</strong>
                <span className="faint num">{shortAddress(data.wallet.address)}</span>
              </div>
              <span className={`badge ${data.wallet.proof_verified_at ? "badge-live" : "badge-wait"}`}>
                {data.wallet.proof_verified_at ? "verified" : "unverified"}
              </span>
            </div>
            <button className="btn btn-danger btn-sm" onClick={() => void disconnect()}>
              Disconnect
            </button>
          </div>
        ) : (
          <div className="stack">
            <p className="faint">
              Link a TON wallet for on-chain features. Your keys stay in your wallet app.
            </p>
            <button className="btn btn-block" onClick={() => void tonConnectUI.openModal()}>
              Connect wallet
            </button>
          </div>
        )}

        {history?.items.length ? (
          <div style={{ marginTop: "var(--sp-4)" }}>
            <span className="section-title">Transactions</span>
            {history.items.slice(0, 5).map((tx) => (
              <div key={tx.id} className="list-item">
                <div className="stack" style={{ gap: 0, flex: 1 }}>
                  <strong className="num" style={{ fontSize: 14 }}>
                    {Number(tx.amount_ton).toFixed(3)} TON
                  </strong>
                  <span className="faint">{relative(tx.created_at)}</span>
                </div>
                <span className={`badge ${tx.status === "confirmed" ? "badge-live" : "badge-wait"}`}>
                  {tx.status}
                </span>
              </div>
            ))}
          </div>
        ) : null}
      </Card>
    </>
  );
}
