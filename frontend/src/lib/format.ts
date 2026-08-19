/** Small formatting helpers. Money is always rendered with tabular numerals. */

export function gg(value: number): string {
  const amount = Math.trunc(value);
  if (Math.abs(amount) >= 1_000_000) return `${(amount / 1_000_000).toFixed(amount % 1_000_000 === 0 ? 0 : 1)}M`;
  if (Math.abs(amount) >= 10_000) return `${(amount / 1000).toFixed(amount % 1000 === 0 ? 0 : 1)}K`;
  return amount.toLocaleString("en-US");
}

export function signed(value: number): string {
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${gg(Math.abs(value))}`;
}

export function multiplier(value: number): string {
  if (!value) return "—";
  return `${value >= 10 ? value.toFixed(1) : value.toFixed(2)}×`;
}

export function percent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function timeLeft(iso: string, now: number = Date.now()): string {
  const diff = new Date(iso).getTime() - now;
  if (diff <= 0) return "ended";

  const seconds = Math.floor(diff / 1000);
  const days = Math.floor(seconds / 86400);
  if (days >= 1) return `${days}d ${Math.floor((seconds % 86400) / 3600)}h`;

  const hours = Math.floor(seconds / 3600);
  if (hours >= 1) return `${hours}h ${Math.floor((seconds % 3600) / 60)}m`;

  const minutes = Math.floor(seconds / 60);
  if (minutes >= 1) return `${minutes}m ${seconds % 60}s`;
  return `${seconds}s`;
}

export function relative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

const TRANSACTION_LABELS: Record<string, string> = {
  stars_topup: "Stars top-up",
  stars_refund: "Stars refund",
  pvp_bet: "PvP entry",
  pvp_win: "PvP win",
  pvp_refund: "PvP refund",
  solo_bet: "Bet",
  solo_win: "Win",
  giveaway_reward: "Giveaway prize",
  referral_bonus: "Referral bonus",
  admin_adjustment: "Adjustment",
};

export function transactionLabel(type: string): string {
  return TRANSACTION_LABELS[type] ?? type.replace(/_/g, " ");
}

export function shortAddress(address: string): string {
  return address.length > 12 ? `${address.slice(0, 6)}…${address.slice(-4)}` : address;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}
