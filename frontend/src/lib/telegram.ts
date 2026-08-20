/**
 * Telegram Mini App integration.
 *
 * The SDK is used for launch parameters, and `window.Telegram.WebApp` for the
 * UI surface (back button, main button, haptics, theme). That combination is
 * deliberate: the global object's shape is stable across Telegram clients,
 * while the SDK gives us a typed way to read the signed launch data.
 *
 * The raw initData string is the only thing the client is trusted to send — the
 * backend verifies its signature before believing anything inside it.
 */

import { init, retrieveLaunchParams } from "@telegram-apps/sdk-react";

type HapticStyle = "light" | "medium" | "heavy" | "rigid" | "soft";
type HapticNotification = "error" | "success" | "warning";

interface TelegramWebApp {
  initData: string;
  initDataUnsafe: Record<string, unknown>;
  version: string;
  platform: string;
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  isExpanded: boolean;
  viewportStableHeight: number;
  ready(): void;
  expand(): void;
  close(): void;
  openLink(url: string, options?: { try_instant_view?: boolean }): void;
  openTelegramLink(url: string): void;
  openInvoice(url: string, callback?: (status: InvoiceStatus) => void): void;
  showPopup?(params: unknown, callback?: (id: string) => void): void;
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
  disableVerticalSwipes?(): void;
  BackButton: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
  MainButton: {
    text: string;
    show(): void;
    hide(): void;
    enable(): void;
    disable(): void;
    showProgress(leaveActive?: boolean): void;
    hideProgress(): void;
    setParams(params: { text?: string; color?: string; text_color?: string; is_active?: boolean; is_visible?: boolean }): void;
    onClick(cb: () => void): void;
    offClick(cb: () => void): void;
  };
  HapticFeedback: {
    impactOccurred(style: HapticStyle): void;
    notificationOccurred(type: HapticNotification): void;
    selectionChanged(): void;
  };
}

export type InvoiceStatus = "paid" | "cancelled" | "failed" | "pending";

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

export const webApp = (): TelegramWebApp | undefined =>
  typeof window !== "undefined" ? window.Telegram?.WebApp : undefined;

export const insideTelegram = (): boolean => Boolean(webApp()?.initData);

/** Call once on boot. Safe to call in a browser tab outside Telegram. */
export function initTelegram(): void {
  const app = webApp();
  if (!app) return; // opened in a plain browser: nothing to initialise

  try {
    init();
  } catch {
    /* older client without the events the SDK expects — the global API still works */
  }

  app.ready();
  app.expand();
  app.setHeaderColor?.("#0a0908");
  app.setBackgroundColor?.("#0a0908");
  // Stops a downward drag inside a game from closing the app mid-round.
  app.disableVerticalSwipes?.();
}

/**
 * The signed launch payload. Never parse or trust it here — hand it to the
 * backend, which validates the HMAC against the bot token.
 */
export function getInitData(): string {
  const app = webApp();
  if (app?.initData) return app.initData;

  try {
    const params = retrieveLaunchParams() as unknown as Record<string, unknown>;
    const raw = params.initDataRaw ?? params.tgWebAppData;
    if (typeof raw === "string") return raw;
  } catch {
    /* not launched from Telegram */
  }
  return "";
}

export function getStartParam(): string | undefined {
  const app = webApp();
  const unsafe = app?.initDataUnsafe as { start_param?: string } | undefined;
  if (unsafe?.start_param) return unsafe.start_param;

  try {
    const params = retrieveLaunchParams() as unknown as Record<string, unknown>;
    const value = params.startParam ?? params.tgWebAppStartParam;
    return typeof value === "string" ? value : undefined;
  } catch {
    return undefined;
  }
}

export const haptics = {
  tap(style: HapticStyle = "light") {
    webApp()?.HapticFeedback?.impactOccurred(style);
  },
  select() {
    webApp()?.HapticFeedback?.selectionChanged();
  },
  notify(type: HapticNotification) {
    webApp()?.HapticFeedback?.notificationOccurred(type);
  },
  win() {
    webApp()?.HapticFeedback?.notificationOccurred("success");
  },
  lose() {
    webApp()?.HapticFeedback?.notificationOccurred("error");
  },
};

export const backButton = {
  show(handler: () => void) {
    const app = webApp();
    if (!app) return () => undefined;
    app.BackButton.onClick(handler);
    app.BackButton.show();
    return () => {
      app.BackButton.offClick(handler);
      app.BackButton.hide();
    };
  },
};

export const mainButton = {
  show(text: string, handler: () => void, options?: { loading?: boolean; disabled?: boolean }) {
    const app = webApp();
    if (!app) return () => undefined;

    app.MainButton.setParams({
      text,
      color: "#ddc9a3",
      text_color: "#17130d",
      is_active: !options?.disabled,
      is_visible: true,
    });
    if (options?.loading) app.MainButton.showProgress(true);
    else app.MainButton.hideProgress();

    app.MainButton.onClick(handler);
    return () => {
      app.MainButton.offClick(handler);
      app.MainButton.hide();
    };
  },
  hide() {
    webApp()?.MainButton.hide();
  },
};

/** Opens a Stars invoice created by the backend. */
export function openInvoice(url: string): Promise<InvoiceStatus> {
  const app = webApp();
  if (!app?.openInvoice) {
    window.open(url, "_blank");
    return Promise.resolve("pending");
  }
  return new Promise((resolve) => app.openInvoice(url, (status) => resolve(status)));
}

export function openTelegramLink(url: string): void {
  const app = webApp();
  if (app?.openTelegramLink) app.openTelegramLink(url);
  else window.open(url, "_blank");
}

export function shareLink(url: string, text: string): void {
  openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`);
}

export function closeApp(): void {
  webApp()?.close();
}
