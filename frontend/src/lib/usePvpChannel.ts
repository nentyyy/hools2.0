/**
 * Realtime PvP feed.
 *
 * Prefers the websocket at /ws/pvp/{id}. Where websockets are unavailable —
 * serverless hosting, a proxy that drops upgrades — it falls back to polling
 * /api/pvp/{id}/state, which returns the same authoritative snapshot plus the
 * events published since the last cursor. Either way the state shown is the
 * state the backend committed.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { PvPGame } from "@shared/index";

import { api, getToken, type PvPEventPayload } from "./api";

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const POLL_INTERVAL = 1500;
const WS_GRACE = 4000;

function socketUrl(gameId: number, token: string): string {
  const base = API_BASE || window.location.origin;
  const url = new URL(`${base}/ws/pvp/${gameId}`);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("token", token);
  return url.toString();
}

export interface PvPChannel {
  game: PvPGame | null;
  events: PvPEventPayload[];
  connected: boolean;
  transport: "websocket" | "polling" | "offline";
  refresh: () => Promise<void>;
}

export function usePvpChannel(gameId: number | null): PvPChannel {
  const [game, setGame] = useState<PvPGame | null>(null);
  const [events, setEvents] = useState<PvPEventPayload[]>([]);
  const [connected, setConnected] = useState(false);
  const [transport, setTransport] = useState<PvPChannel["transport"]>("offline");

  const cursor = useRef(0);
  const socket = useRef<WebSocket | null>(null);
  const poller = useRef<number | null>(null);

  const pushEvent = useCallback((event: PvPEventPayload) => {
    setEvents((current) => [...current.slice(-40), event]);
  }, []);

  const refresh = useCallback(async () => {
    if (!gameId) return;
    const state = await api.pvpState(gameId, cursor.current);
    cursor.current = state.cursor;
    setGame(state.game);
    for (const event of state.events) pushEvent(event);
  }, [gameId, pushEvent]);

  useEffect(() => {
    if (!gameId) return;
    let disposed = false;

    const startPolling = () => {
      if (poller.current || disposed) return;
      setTransport("polling");
      const tick = async () => {
        try {
          await refresh();
          setConnected(true);
        } catch {
          setConnected(false);
        }
      };
      void tick();
      poller.current = window.setInterval(tick, POLL_INTERVAL);
    };

    const stopPolling = () => {
      if (poller.current) {
        window.clearInterval(poller.current);
        poller.current = null;
      }
    };

    // Load the snapshot immediately so the screen is never empty.
    void refresh().catch(() => undefined);

    const token = getToken();
    let fallbackTimer = 0;

    if (token && "WebSocket" in window) {
      try {
        const ws = new WebSocket(socketUrl(gameId, token));
        socket.current = ws;
        // If the socket has not opened shortly, start polling alongside it.
        fallbackTimer = window.setTimeout(startPolling, WS_GRACE);

        ws.onopen = () => {
          if (disposed) return;
          window.clearTimeout(fallbackTimer);
          stopPolling();
          setConnected(true);
          setTransport("websocket");
        };

        ws.onmessage = (message) => {
          try {
            const payload = JSON.parse(message.data) as PvPEventPayload;
            if (payload.event === "state") {
              setGame(payload.data as unknown as PvPGame);
            } else if (payload.event !== "heartbeat" && payload.event !== "pong") {
              pushEvent(payload);
              // Any event may have changed the round; re-read the snapshot.
              void refresh().catch(() => undefined);
            }
          } catch {
            /* ignore malformed frames */
          }
        };

        ws.onerror = () => startPolling();
        ws.onclose = () => {
          setConnected(false);
          if (!disposed) startPolling();
        };
      } catch {
        startPolling();
      }
    } else {
      startPolling();
    }

    const keepAlive = window.setInterval(() => {
      if (socket.current?.readyState === WebSocket.OPEN) socket.current.send("ping");
    }, 20000);

    return () => {
      disposed = true;
      window.clearTimeout(fallbackTimer);
      window.clearInterval(keepAlive);
      stopPolling();
      socket.current?.close();
      socket.current = null;
    };
  }, [gameId, refresh, pushEvent]);

  return { game, events, connected, transport, refresh };
}

/** Seconds remaining until `iso`, ticking once per second. */
export function useCountdown(iso: string | null): number {
  const [left, setLeft] = useState(() => remaining(iso));

  useEffect(() => {
    setLeft(remaining(iso));
    if (!iso) return;
    const timer = window.setInterval(() => setLeft(remaining(iso)), 250);
    return () => window.clearInterval(timer);
  }, [iso]);

  return left;
}

function remaining(iso: string | null): number {
  if (!iso) return 0;
  return Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 1000));
}
