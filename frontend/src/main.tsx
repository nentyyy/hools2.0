import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TonConnectUIProvider } from "@tonconnect/ui-react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";

import App from "./App";
import { SessionProvider } from "./lib/session";
import { initTelegram } from "./lib/telegram";
import { ToastProvider } from "./lib/toast";
import "./styles/global.css";

initTelegram();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // Auth and validation failures will not fix themselves.
        const status = (error as { status?: number }).status ?? 0;
        if (status >= 400 && status < 500) return false;
        return failureCount < 2;
      },
      staleTime: 10_000,
      refetchOnWindowFocus: false,
    },
  },
});

// Hash routing keeps deep links working inside Telegram, where the app may be
// opened at an arbitrary path with a start parameter appended.
const manifestUrl =
  import.meta.env.VITE_TON_MANIFEST_URL ?? `${window.location.origin}/tonconnect-manifest.json`;

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <TonConnectUIProvider manifestUrl={manifestUrl}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <SessionProvider>
            <HashRouter>
              <App />
            </HashRouter>
          </SessionProvider>
        </ToastProvider>
      </QueryClientProvider>
    </TonConnectUIProvider>
  </StrictMode>,
);
