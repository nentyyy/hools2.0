/**
 * Session state.
 *
 * On boot we hand the signed Telegram initData to the backend and keep the JWT
 * it returns. The balance held here is only ever the value the backend last
 * reported — it is never incremented locally after a bet.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import type { User } from "@shared/index";

import { ApiError, api, getToken, setToken } from "./api";
import { getDeviceId } from "./device";
import { getInitData, getStartParam } from "./telegram";

interface SessionValue {
  user: User | null;
  status: "loading" | "ready" | "error";
  isGuest: boolean;
  error: string | null;
  balance: number;
  setBalance: (value: number) => void;
  refresh: () => Promise<void>;
  retry: () => void;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<SessionValue["status"]>("loading");
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function boot() {
      setStatus("loading");
      setError(null);
      try {
        // An existing token survives a reload; fall back to a fresh handshake.
        if (getToken()) {
          try {
            const me = await api.me();
            if (!cancelled) {
              setUser(me);
              setStatus("ready");
            }
            return;
          } catch (err) {
            if (!(err instanceof ApiError) || err.status !== 401) throw err;
          }
        }

        const initData = getInitData();

        // Outside Telegram there is no signed launch data, so fall back to a
        // guest account — which the backend only issues when browser play is
        // explicitly enabled for the deployment.
        const auth = initData
          ? await api.authenticate(initData, getStartParam())
          : await api.authenticateGuest(getDeviceId(), getStartParam()).catch((error: unknown) => {
              if (error instanceof ApiError && error.status === 403) {
                throw new ApiError(
                  "not_in_telegram",
                  "Open this app from Telegram to sign in.",
                  403,
                );
              }
              throw error;
            });
        setToken(auth.token);
        if (!cancelled) {
          setUser(auth.user);
          setStatus("ready");
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Sign-in failed");
        setStatus("error");
      }
    }

    void boot();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const refresh = useCallback(async () => {
    try {
      setUser(await api.me());
    } catch {
      /* a transient failure must not blank the screen */
    }
  }, []);

  const setBalance = useCallback((value: number) => {
    setUser((current) => (current ? { ...current, balance: value } : current));
  }, []);

  const value = useMemo<SessionValue>(
    () => ({
      user,
      status,
      error,
      // Guests live in a reserved negative id range on the backend.
      isGuest: (user?.telegram_id ?? 0) < 0,
      balance: user?.balance ?? 0,
      setBalance,
      refresh,
      retry: () => setAttempt((n) => n + 1),
    }),
    [user, status, error, setBalance, refresh],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside SessionProvider");
  return context;
}
