/**
 * Stable per-device identifier for browser (guest) play.
 *
 * It is not a credential: the backend derives a guest account from it, and a
 * guest can never be an administrator. Keeping it in local storage is what lets
 * a browser player come back to the same balance.
 */

const KEY = "gg.device";

export function getDeviceId(): string {
  try {
    const existing = localStorage.getItem(KEY);
    if (existing && existing.length >= 8) return existing;

    const created = crypto.randomUUID?.() ?? `dev-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem(KEY, created);
    return created;
  } catch {
    // Private mode: a per-session identity is still better than none.
    return `session-${Math.random().toString(36).slice(2)}-${Date.now()}`;
  }
}
