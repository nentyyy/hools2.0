/**
 * Theme access for the canvas surfaces.
 *
 * CSS custom properties are the single source of truth for colour; canvas
 * cannot read them on its own, so it asks for them here. Retuning the palette
 * in global.css then moves the wheel, the board and the rink with it.
 */

const cache = new Map<string, string>();

export function cssVar(name: string, fallback = "#000000"): string {
  const cached = cache.get(name);
  if (cached) return cached;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const resolved = value || fallback;
  cache.set(name, resolved);
  return resolved;
}

/** Clear after a palette change (theme switch, hot reload). */
export function resetThemeCache(): void {
  cache.clear();
}

/**
 * Slice colours for the wheel and the rink: a sand-to-ember ramp that stays
 * inside the black-and-beige world while keeping neighbouring players apart.
 */
export const PLAYER_COLORS = [
  "#ddc9a3",
  "#a8b98f",
  "#d08a76",
  "#c8a06a",
  "#9a8b78",
  "#e6d7b4",
  "#b9765f",
  "#8fae8b",
  "#e8a95f",
  "#7d6a58",
  "#c0a6d6",
  "#b3a894",
];
