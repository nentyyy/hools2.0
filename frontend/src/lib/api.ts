/**
 * Typed API client.
 *
 * Responsibilities that matter for correctness:
 *  - attaches the session JWT obtained from `/auth/telegram`;
 *  - sends an `X-Idempotency-Key` on every mutating call, so a retry after a
 *    dropped connection can never place a second bet or a second payment;
 *  - surfaces backend error codes as a typed `ApiError` the UI can react to.
 *
 * The client never computes a game result or a balance: it only renders what
 * the backend returns.
 */

import type {
  GGPackage,
  Giveaway,
  InventoryItem,
  LevelInfo,
  Page,
  PvPGame,
  SoloGame,
  Transaction,
  User,
} from "@shared/index";

const BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const TOKEN_KEY = "gg.token";

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
    readonly details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let token: string | null = null;

export function getToken(): string | null {
  if (token) return token;
  try {
    token = localStorage.getItem(TOKEN_KEY);
  } catch {
    token = null;
  }
  return token;
}

export function setToken(value: string | null): void {
  token = value;
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode: keep the token in memory only */
  }
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  idempotencyKey?: string;
  signal?: AbortSignal;
  auth?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, idempotencyKey, signal, auth = true } = options;
  const headers: Record<string, string> = { Accept: "application/json" };

  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const current = getToken();
    if (current) headers.Authorization = `Bearer ${current}`;
  }
  // Mutating requests are always keyed, even when the caller did not pass one.
  if (method !== "GET") headers["X-Idempotency-Key"] = idempotencyKey ?? newIdempotencyKey();

  const response = await fetch(`${BASE}/api${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload = text ? safeParse(text) : null;

  if (!response.ok) {
    const error = (payload as { error?: { code: string; message: string; details?: Record<string, unknown> } })?.error;
    if (response.status === 401) setToken(null);
    throw new ApiError(
      error?.code ?? "http_error",
      error?.message ?? `Request failed with status ${response.status}`,
      response.status,
      error?.details,
    );
  }
  return payload as T;
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/* ----------------------------- auth & profile ---------------------------- */

export interface AuthResponse {
  token: string;
  expires_in: number;
  user: User;
  is_new: boolean;
}

export interface ProfileResponse {
  user: User;
  level: LevelInfo;
  stats: {
    pvp_wins: number;
    pvp_games: number;
    solo_wins: number;
    solo_games: number;
    total_wagered: number;
    total_earned: number;
    stars_spent: number;
  };
  referrals: { code: string; link: string; invited_count: number; earnings: number };
  inventory: InventoryItem[];
  transactions: Transaction[];
}

export interface ReferralsResponse {
  code: string;
  link: string;
  invited_count: number;
  earnings: number;
  signup_bonus: number;
  topup_percent: number;
  referrals: {
    id: number;
    name: string;
    username: string | null;
    avatar: string | null;
    level: number;
    joined_at: string;
  }[];
}

export const api = {
  authenticate: (initData: string, startParam?: string) =>
    request<AuthResponse>("/auth/telegram", {
      method: "POST",
      body: { init_data: initData, start_param: startParam },
      auth: false,
    }),

  authenticateGuest: (deviceId: string, startParam?: string) =>
    request<AuthResponse>("/auth/guest", {
      method: "POST",
      body: { device_id: deviceId, start_param: startParam },
      auth: false,
    }),

  authModes: () => request<{ telegram: boolean; guest: boolean }>("/auth/modes", { auth: false }),

  me: () => request<User>("/me"),
  balance: () => request<{ balance: number; currency: string }>("/balance"),
  profile: () => request<ProfileResponse>("/profile"),
  referrals: () => request<ReferralsResponse>("/referrals"),

  transactions: (params: { limit?: number; offset?: number; type?: string } = {}) =>
    request<Page<Transaction>>(`/transactions${query(params)}`),

  inventory: (params: { limit?: number; offset?: number; include_sold?: boolean } = {}) =>
    request<Page<InventoryItem>>(`/inventory${query(params)}`),
  inventoryItem: (id: number) => request<InventoryItem>(`/inventory/${id}`),
  sellItem: (id: number, key: string) =>
    request<{ ok: boolean; payout: number; balance: number; item_id: number }>(
      `/inventory/${id}/sell`,
      { method: "POST", idempotencyKey: key },
    ),

  fairness: () =>
    request<{
      server_seed_hash: string;
      client_seed: string;
      nonce: number;
      previous_server_seed: string | null;
      previous_server_seed_hash: string | null;
    }>("/fair"),

  /* ---------------------------------- PvP -------------------------------- */
  pvpList: (params: { status?: string; limit?: number } = {}) =>
    request<{ items: PvPGame[]; config: PvPConfig }>(`/pvp${query(params)}`),
  pvpGame: (id: number) => request<{ game: PvPGame }>(`/pvp/${id}`),
  pvpState: (id: number, cursor = 0) =>
    request<{ game: PvPGame; events: PvPEventPayload[]; cursor: number }>(
      `/pvp/${id}/state${query({ cursor })}`,
    ),
  pvpCreate: (amount: number, key: string) =>
    request<{ game: PvPGame; balance: number }>("/pvp/create", {
      method: "POST",
      body: { amount },
      idempotencyKey: key,
    }),
  pvpJoin: (id: number, amount: number, key: string) =>
    request<{ game: PvPGame; balance: number }>(`/pvp/${id}/join`, {
      method: "POST",
      body: { amount },
      idempotencyKey: key,
    }),

  /* --------------------------------- Solo -------------------------------- */
  soloConfig: () => request<SoloConfig>("/solo/config"),
  soloActive: () => request<{ hi_lo: HiLoState | null; ice_arena: IceArenaState | null }>("/solo/active"),
  soloHistory: (params: { game_type?: string; limit?: number; offset?: number } = {}) =>
    request<Page<SoloGame>>(`/solo/history${query(params)}`),

  playPlinko: (body: { bet: number; rows: number; risk: string }, key: string) =>
    request<SoloPlayResponse>("/solo/plinko/play", { method: "POST", body, idempotencyKey: key }),
  playUpgrade: (body: { bet: number; target: number }, key: string) =>
    request<SoloPlayResponse>("/solo/upgrade/play", { method: "POST", body, idempotencyKey: key }),
  playLuckyBuy: (body: { case: string }, key: string) =>
    request<SoloPlayResponse & { item: DropItem }>("/solo/lucky-buy/play", {
      method: "POST",
      body,
      idempotencyKey: key,
    }),
  playHiLo: (
    body: { action: "start" | "guess" | "cash_out"; bet?: number; game_id?: number; choice?: string },
    key: string,
  ) => request<SoloPlayResponse<HiLoState>>("/solo/hilo/play", { method: "POST", body, idempotencyKey: key }),
  playIceArena: (
    body: { action: "start" | "advance" | "cash_out"; bet?: number; game_id?: number; difficulty?: string },
    key: string,
  ) =>
    request<SoloPlayResponse<IceArenaState>>("/solo/ice-arena/play", {
      method: "POST",
      body,
      idempotencyKey: key,
    }),

  /* ------------------------------ giveaways ------------------------------ */
  giveaways: (params: { status?: string; limit?: number; offset?: number } = {}) =>
    request<Page<Giveaway>>(`/giveaways${query(params)}`),
  giveaway: (id: number) => request<Giveaway>(`/giveaways/${id}`),
  joinGiveaway: (id: number, key: string) =>
    request<Giveaway & { balance: number }>(`/giveaways/${id}/join`, {
      method: "POST",
      idempotencyKey: key,
    }),
  giveawayParticipants: (id: number, params: { limit?: number; offset?: number } = {}) =>
    request<Page<{ user_id: number; name: string; avatar: string | null; level: number; joined_at: string }>>(
      `/giveaways/${id}/participants${query(params)}`,
    ),

  /* ------------------------------- payments ------------------------------ */
  packages: () => request<GGPackage[]>("/payments/packages"),
  createInvoice: (packageCode: string, key: string) =>
    request<{ payment_id: number; invoice_link: string; payload: string; stars: number; gg: number }>(
      "/payments/stars/create",
      { method: "POST", body: { package: packageCode }, idempotencyKey: key },
    ),
  paymentHistory: (params: { limit?: number; offset?: number } = {}) =>
    request<Page<StarPayment>>(`/payments/history${query(params)}`),
  paySupport: () => request<{ text: string }>("/payments/support"),

  /* ---------------------------------- TON -------------------------------- */
  tonWallet: () => request<TonWalletResponse>("/ton/wallet"),
  tonConnect: (body: TonConnectBody, key: string) =>
    request<TonWallet>("/ton/connect", { method: "POST", body, idempotencyKey: key }),
  tonDisconnect: (key: string) =>
    request<{ ok: boolean }>("/ton/disconnect", { method: "POST", idempotencyKey: key }),
  tonVerify: (body: { boc_hash: string; tx_hash?: string; comment?: string; purpose?: string }, key: string) =>
    request<TonTransaction>("/ton/verify", { method: "POST", body, idempotencyKey: key }),
  tonTransactions: () =>
    request<{ items: TonTransaction[]; receiver_address: string | null }>("/ton/transactions"),
};

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

/* --------------------------------- types --------------------------------- */

export interface PvPConfig {
  min_bet: number;
  max_bet: number;
  rake_percent: number;
  countdown_seconds: number;
  spin_seconds: number;
  max_players: number;
}

export interface PvPEventPayload {
  event: string;
  game_id: number;
  data: Record<string, unknown>;
}

export interface SoloPlayResponse<S = Record<string, unknown>> {
  game: SoloGame;
  balance: number;
  state: S | null;
}

export interface DropItem {
  id: number;
  name: string;
  rarity: string;
  gg_value: number;
  code: string;
}

export interface SoloConfig {
  limits: { min_bet: number; max_bet: number };
  house_edge: number;
  plinko: { rows: number[]; risks: string[]; tables: Record<string, number[]> };
  upgrade: { min_target: number; max_target: number; presets: { target: number; chance: number }[] };
  lucky_buy: {
    cases: {
      code: string;
      title: string;
      price: number;
      items: { code: string; name: string; rarity: string; chance: number; gg_value: number }[];
    }[];
  };
  hi_lo: { max_rounds: number; choices: string[] };
  ice_arena: { max_rounds: number; difficulties: { difficulty: string; chance: number; step: number }[] };
}

export interface HiLoState {
  game_id: number;
  status: string;
  bet: number;
  card: number;
  card_label: string;
  suit: string | null;
  round: number;
  multiplier: number;
  potential_reward: number;
  history: { round: number; card: number; next_card: number; choice: string; won: boolean; step: number }[];
  odds: Record<string, { chance: number; multiplier: number }>;
  max_rounds: number;
}

export interface IceArenaState {
  game_id: number;
  status: string;
  bet: number;
  round: number;
  max_rounds: number;
  multiplier: number;
  potential_reward: number;
  history: { round: number; difficulty: string; chance: number; step: number; survived: boolean; reward: number }[];
  options: { difficulty: string; chance: number; step: number; reward: number }[];
}

export interface StarPayment {
  id: number;
  package_code: string;
  gg_amount: number;
  stars_amount: number;
  currency: string;
  status: string;
  telegram_payment_charge_id: string | null;
  created_at: string;
  paid_at: string | null;
  refunded_at: string | null;
}

export interface TonWallet {
  address: string;
  friendly_address: string | null;
  chain: string | null;
  wallet_name: string | null;
  proof_verified_at: string | null;
  connected_at: string | null;
}

export interface TonWalletResponse {
  connected: boolean;
  wallet: TonWallet | null;
  proof_payload: string | null;
  receiver_address: string | null;
  manifest_url: string | null;
}

export interface TonConnectBody {
  address: string;
  public_key?: string;
  friendly_address?: string;
  chain?: string;
  wallet_name?: string;
  proof?: {
    timestamp: number;
    domain: { lengthBytes?: number; value: string };
    signature: string;
    payload: string;
  };
}

export interface TonTransaction {
  id: number;
  boc_hash: string;
  tx_hash: string | null;
  from_address: string | null;
  to_address: string | null;
  amount_nano: number;
  amount_ton: number;
  comment: string | null;
  purpose: string | null;
  status: string;
  created_at: string;
  confirmed_at: string | null;
}
