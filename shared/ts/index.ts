/**
 * Types and constants shared between the frontend and the backend.
 * Mirrors `shared/gg_shared/constants.py` — keep the two in step.
 */

export const TransactionType = {
  StarsTopup: "stars_topup",
  StarsRefund: "stars_refund",
  PvpBet: "pvp_bet",
  PvpWin: "pvp_win",
  PvpRefund: "pvp_refund",
  SoloBet: "solo_bet",
  SoloWin: "solo_win",
  GiveawayReward: "giveaway_reward",
  ReferralBonus: "referral_bonus",
  AdminAdjustment: "admin_adjustment",
} as const;
export type TransactionType = (typeof TransactionType)[keyof typeof TransactionType];

export type PvPStatus = "waiting" | "starting" | "spinning" | "finished" | "cancelled";
export type SoloGameType = "plinko" | "upgrade" | "lucky_buy" | "hi_lo" | "ice_arena";
export type SoloStatus = "active" | "finished" | "cashed_out" | "lost";
export type GiveawayStatus = "draft" | "active" | "finished" | "cancelled";
export type ItemRarity = "common" | "uncommon" | "rare" | "epic" | "legendary";

export type PvPEventName =
  | "player_joined"
  | "player_left"
  | "balance_updated"
  | "game_started"
  | "countdown"
  | "wheel_started"
  | "winner_selected"
  | "game_finished"
  | "state"
  | "heartbeat"
  | "pong"
  | "error";

export interface User {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  avatar: string | null;
  balance: number;
  xp: number;
  level: number;
  is_banned: boolean;
  is_admin: boolean;
  referral_code: string;
  referral_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface LevelInfo {
  level: number;
  xp: number;
  xp_into_level: number;
  xp_needed: number;
  xp_next_level: number;
  progress: number;
}

export interface Transaction {
  id: number;
  type: TransactionType;
  amount: number;
  balance_before: number;
  balance_after: number;
  reference_id: string | null;
  description: string | null;
  created_at: string;
}

export interface InventoryItem {
  id: number;
  item_type: string;
  item_code: string;
  name: string;
  image: string | null;
  rarity: ItemRarity;
  quantity: number;
  gg_value: number;
  is_sold: boolean;
  source: string | null;
  created_at: string;
}

export interface PvPPlayer {
  user_id: number;
  name: string;
  username: string | null;
  avatar: string | null;
  amount: number;
  chance: number;
  ticket_from: number;
  ticket_to: number;
  is_winner: boolean;
}

export interface PvPGame {
  id: number;
  status: PvPStatus;
  total_pool: number;
  prize: number;
  rake: number;
  min_bet: number;
  max_players: number;
  creator_id: number;
  winner_id: number | null;
  players: PvPPlayer[];
  created_at: string;
  started_at: string | null;
  spin_at: string | null;
  finished_at: string | null;
  server_seed_hash: string;
  server_seed: string | null;
  client_seed: string;
  nonce: number;
  winning_roll: number | null;
  countdown_seconds: number;
  spin_seconds: number;
  server_time: string;
}

export interface SoloGame {
  id: number;
  game_type: SoloGameType;
  status: SoloStatus;
  bet: number;
  reward: number;
  multiplier: number;
  result: Record<string, unknown> | null;
  state: Record<string, unknown> | null;
  server_seed_hash: string;
  server_seed: string | null;
  client_seed: string;
  nonce: number;
  created_at: string;
  finished_at: string | null;
}

export interface Giveaway {
  id: number;
  title: string;
  description: string | null;
  image: string | null;
  prize_type: string;
  prize_value: number;
  entry_cost: number;
  min_level: number;
  max_participants: number | null;
  participants_count: number;
  start_at: string;
  end_at: string;
  status: GiveawayStatus;
  winner_id: number | null;
  finished_at: string | null;
  created_at: string;
  joined?: boolean;
  winner?: { id: number; name: string; username: string | null; avatar: string | null } | null;
}

export interface GGPackage {
  code: string;
  title: string;
  gg: number;
  bonus_gg: number;
  total_gg: number;
  stars: number;
  currency: "XTR";
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export const RARITY_ORDER: ItemRarity[] = ["common", "uncommon", "rare", "epic", "legendary"];

export const SOLO_MODES: { type: SoloGameType; slug: string; title: string; blurb: string }[] = [
  { type: "plinko", slug: "plinko", title: "Plinko", blurb: "Drop the ball, chase the edges" },
  { type: "upgrade", slug: "upgrade", title: "Upgrade", blurb: "Pick a multiplier, take the odds" },
  { type: "hi_lo", slug: "hi-lo", title: "Hi-Lo", blurb: "Higher or lower, stack the streak" },
  { type: "ice_arena", slug: "ice-arena", title: "Ice Arena", blurb: "Cross the ice, cash out in time" },
];
